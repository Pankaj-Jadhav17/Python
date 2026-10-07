import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_CONFIDENCE_THRESHOLD,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TIMEOUT_SECONDS,
)
from app.services.pdf_graph_service import PDFGraphService

logger = logging.getLogger(__name__)

ALLOWED_RELATIONS = {
    "associated with",
    "contains",
    "contributes to",
    "develops into",
    "enables",
    "forms",
    "fuses with",
    "inhibits",
    "is a stage of",
    "is part of",
    "is the site of",
    "leads to",
    "matures into",
    "nourishes",
    "occurs in",
    "participates in",
    "pollinates",
    "produces",
    "produces without fertilisation",
    "releases",
    "represents",
    "requires",
    "supports",
    "undergoes",
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string", "enum": sorted(ALLOWED_RELATIONS)},
                    "object": {"type": "string"},
                    "evidence": {"type": "string", "maxLength": 180},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["subject", "relation", "object", "evidence", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["triples"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["verified", "rejected", "pending"]},
        "reason": {"type": "string"},
    },
    "required": ["decision", "reason"],
    "additionalProperties": False,
}

CANONICAL_ALIASES = {
    "pmc": "pollen mother cell",
    "p.m.c.": "pollen mother cell",
    "mmc": "megaspore mother cell",
    "m.m.c.": "megaspore mother cell",
    "pec": "primary endosperm cell",
}


@dataclass(frozen=True)
class PassageChunk:
    passage_id: str
    page: int | None
    start_offset: int
    end_offset: int
    text: str


class EvidenceGraphService(PDFGraphService):
    """Build a provenance-preserving concept graph using local Ollama extraction."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        ollama_base_url: str | None = None,
        model: str | None = None,
        confidence_threshold: float | None = None,
    ):
        super().__init__(uri=uri, user=user, password=password)
        self.ollama_base_url = (ollama_base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL
        self.confidence_threshold = (
            OLLAMA_CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold
        )

    def iter_passages(
        self,
        file_path: str,
        extension: str,
        document_name: str,
        start_page: int | None = None,
        end_page: int | None = None,
        max_chars: int = 2400,
        overlap: int = 180,
    ) -> Iterable[PassageChunk]:
        if extension == ".pdf":
            import pymupdf

            try:
                with pymupdf.open(file_path) as document:
                    if document.needs_pass:
                        raise ValueError("This PDF is password-protected. Remove its password and upload it again.")
                    first_page = start_page or 1
                    last_page = end_page or document.page_count
                    if first_page > document.page_count or last_page > document.page_count:
                        raise ValueError(f"This PDF has {document.page_count} pages; the requested range is out of bounds.")
                    if first_page > last_page:
                        raise ValueError("The starting page must be less than or equal to the ending page.")
                    for page_number in range(first_page - 1, last_page):
                        text = document.load_page(page_number).get_text("text", sort=True)
                        yield from self._split_passage_text(text, document_name, page_number + 1, max_chars, overlap)
            except ValueError:
                raise
            except Exception as error:
                raise ValueError(f"Could not parse this PDF with PyMuPDF: {error}") from error
            return

        if extension == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="replace") as text_file:
                offset = 0
                while text := text_file.read(max_chars):
                    for passage in self._split_passage_text(text, document_name, None, max_chars, overlap):
                        yield PassageChunk(
                            passage_id=self._passage_id(document_name, None, offset + passage.start_offset, text),
                            page=None,
                            start_offset=offset + passage.start_offset,
                            end_offset=offset + passage.end_offset,
                            text=passage.text,
                        )
                    offset += len(text)
            return

        paragraph_offset = 0
        for paragraph in self.iter_text_chunks(file_path, extension):
            for passage in self._split_passage_text(paragraph, document_name, None, max_chars, overlap):
                yield PassageChunk(
                    passage_id=self._passage_id(document_name, None, paragraph_offset + passage.start_offset, paragraph),
                    page=None,
                    start_offset=paragraph_offset + passage.start_offset,
                    end_offset=paragraph_offset + passage.end_offset,
                    text=passage.text,
                )
            paragraph_offset += len(paragraph) + 1

    @staticmethod
    def _passage_id(document_name: str, page: int | None, start_offset: int, text: str) -> str:
        identity = f"{document_name}|{page}|{start_offset}|{text}".encode("utf-8")
        return hashlib.sha256(identity).hexdigest()[:24]

    def _split_passage_text(
        self,
        text: str,
        document_name: str,
        page: int | None,
        max_chars: int,
        overlap: int,
    ) -> Iterable[PassageChunk]:
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = max(text.rfind(mark, start + max_chars // 2, end) for mark in (". ", "; ", "\n", " "))
                if boundary > start:
                    end = boundary + (1 if text[boundary] in ".;" else 0)
            passage_text = text[start:end]
            if passage_text.strip():
                yield PassageChunk(
                    passage_id=self._passage_id(document_name, page, start, passage_text),
                    page=page,
                    start_offset=start,
                    end_offset=end,
                    text=passage_text,
                )
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)

    def _call_ollama(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_predict": OLLAMA_NUM_PREDICT},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.ollama_base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
            return json.loads(result["message"]["content"])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
            raise RuntimeError(f"Ollama request failed for model {self.model}: {error}") from error

    def check_ollama(self) -> None:
        request = urllib.request.Request(f"{self.ollama_base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                models = json.loads(response.read().decode("utf-8")).get("models", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.ollama_base_url}. Start Ollama and retry."
            ) from error
        available = {model.get("name") for model in models}
        if self.model not in available:
            raise RuntimeError(
                f"Ollama model '{self.model}' is not installed. Available models: {', '.join(sorted(available)) or 'none'}. "
                f"Install it with: ollama pull {self.model}"
            )

    def extract_candidates(self, passage: PassageChunk) -> list[dict]:
        prompt = (
            f"Passage ID: {passage.passage_id}\n"
            f"PDF page: {passage.page}\n"
            f"Character offsets: {passage.start_offset}-{passage.end_offset}\n"
            "Extract only explicit factual relationships stated in this passage, at most two triples. "
            "Stop after two triples even if more relationships are present. "
            "Use short subject and object concept names, one allowed relation, an exact verbatim evidence quote under 180 characters, "
            "and confidence from 0 to 1. Do not infer facts or use outside knowledge. "
            f"Allowed relations: {', '.join(sorted(ALLOWED_RELATIONS))}.\n\n"
            f"PASSAGE:\n{passage.text}"
        )
        result = self._call_ollama(
            "You extract evidence-grounded subject-relation-object triples from biology text. "
            "Return only the requested JSON schema. Evidence must be copied exactly from the passage.",
            prompt,
            EXTRACTION_SCHEMA,
        )
        triples = result.get("triples")
        if not isinstance(triples, list):
            raise ValueError("Ollama response is missing the triples list.")
        return triples

    def review_candidate(self, passage: PassageChunk, candidate: dict) -> dict:
        prompt = (
            "Independently check whether this triple's exact evidence quote supports the stated relationship. "
            "The subject and object must both be present in the evidence. Do not use outside knowledge. "
            "Return verified only when the evidence unambiguously supports the triple; otherwise return rejected "
            "for contradicted/unsupported claims or pending when uncertain.\n"
            f"TRIPLE: {json.dumps(candidate, ensure_ascii=False)}\n"
            f"PASSAGE:\n{passage.text}"
        )
        return self._call_ollama(
            "You are an independent evidence reviewer. Return only the requested JSON schema.",
            prompt,
            REVIEW_SCHEMA,
        )

    @staticmethod
    def _normalize_match(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @classmethod
    def _contains_phrase(cls, text: str, phrase: str) -> bool:
        normalized_text = cls._normalize_match(text)
        normalized_phrase = cls._normalize_match(phrase)
        if not normalized_phrase:
            return False
        pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
        return re.search(pattern, normalized_text) is not None

    def validate_candidate(self, passage: PassageChunk, candidate: dict) -> tuple[dict | None, str | None]:
        if not isinstance(candidate, dict):
            return None, "candidate is not a JSON object"
        subject = candidate.get("subject")
        relation = candidate.get("relation")
        object_name = candidate.get("object")
        evidence = candidate.get("evidence")
        try:
            confidence = float(candidate.get("confidence"))
        except (TypeError, ValueError):
            return None, "confidence is not numeric"
        if not all(isinstance(value, str) and value.strip() for value in (subject, relation, object_name, evidence)):
            return None, "subject, relation, object, and evidence must be non-empty strings"
        relation = re.sub(r"\s+", " ", relation.strip().lower().replace("_", " "))
        if relation not in ALLOWED_RELATIONS:
            return None, f"relation is not allowed: {relation}"
        if not 0 <= confidence <= 1:
            return None, "confidence must be between 0 and 1"
        if not self._contains_phrase(passage.text, evidence):
            return None, "evidence quote does not occur in the passage"
        if not self._contains_phrase(evidence, subject):
            return None, "subject does not occur in the evidence quote"
        if not self._contains_phrase(evidence, object_name):
            return None, "object does not occur in the evidence quote"
        return {
            "subject": re.sub(r"\s+", " ", subject).strip(),
            "relation": relation,
            "object": re.sub(r"\s+", " ", object_name).strip(),
            "evidence": evidence.strip(),
            "confidence": confidence,
        }, None

    def _resolve_concepts(self, concepts: set[str]) -> tuple[dict[str, str], dict[str, set[str]]]:
        with self.driver.session() as session:
            records = session.run("MATCH (c:Concept) RETURN c.canonical_name AS canonical_name, c.aliases AS aliases")
            existing = [dict(record) for record in records]

        known_aliases: dict[str, str] = {}
        for record in existing:
            canonical = record.get("canonical_name")
            if not canonical:
                continue
            known_aliases[self._normalize_match(canonical)] = canonical
            for alias in record.get("aliases") or []:
                known_aliases[self._normalize_match(alias)] = canonical

        canonical_by_surface: dict[str, str] = {}
        aliases_by_canonical: dict[str, set[str]] = {}
        for surface in concepts:
            normalized = self._normalize_match(surface)
            static_canonical = CANONICAL_ALIASES.get(normalized, normalized)
            canonical = known_aliases.get(normalized) or known_aliases.get(static_canonical) or static_canonical
            canonical_by_surface[surface] = canonical
            aliases_by_canonical.setdefault(canonical, set()).add(surface)
            if surface != canonical:
                aliases_by_canonical[canonical].add(surface)
        return canonical_by_surface, aliases_by_canonical

    def create_evidence_graph(self, document_name: str, passages: Iterable[PassageChunk]) -> dict:
        passage_records: dict[str, dict] = {}
        relationship_records: dict[str, dict] = {}
        attempts: dict[str, dict] = {}
        rejected = 0
        pending = 0

        for passage in passages:
            passage_records[passage.passage_id] = asdict(passage)
            try:
                candidates = self.extract_candidates(passage)
            except Exception as error:
                logger.exception("Ollama extraction failed for passage %s", passage.passage_id)
                attempt_id = hashlib.sha256(f"{passage.passage_id}|extract-error".encode()).hexdigest()[:24]
                attempts[attempt_id] = {
                    "id": attempt_id,
                    "document_name": document_name,
                    "passage_id": passage.passage_id,
                    "status": "rejected",
                    "reason": str(error),
                    "raw_candidate": "",
                }
                rejected += 1
                continue

            for index, raw_candidate in enumerate(candidates):
                candidate_id = hashlib.sha256(
                    f"{passage.passage_id}|{index}|{json.dumps(raw_candidate, sort_keys=True, ensure_ascii=False)}".encode()
                ).hexdigest()[:24]
                candidate, reason = self.validate_candidate(passage, raw_candidate)
                if reason:
                    logger.warning("Rejected triple %s from passage %s: %s", candidate_id, passage.passage_id, reason)
                    attempts[candidate_id] = self._attempt_record(
                        candidate_id, document_name, passage, "rejected", reason, raw_candidate
                    )
                    rejected += 1
                    continue

                review_reason = "confidence met threshold"
                status = "verified"
                if candidate["confidence"] < self.confidence_threshold:
                    try:
                        review = self.review_candidate(passage, candidate)
                        status = review.get("decision", "pending")
                        review_reason = str(review.get("reason", "No review reason returned"))[:1000]
                        if status not in {"verified", "rejected", "pending"}:
                            status = "pending"
                            review_reason = "Ollama returned an invalid review status"
                    except Exception as error:
                        logger.exception("Ollama review failed for triple %s", candidate_id)
                        status = "pending"
                        review_reason = f"Second-pass review unavailable: {error}"[:1000]

                attempts[candidate_id] = self._attempt_record(
                    candidate_id, document_name, passage, status, review_reason, raw_candidate, candidate
                )
                if status == "rejected":
                    rejected += 1
                    logger.warning("Second-pass review rejected triple %s: %s", candidate_id, review_reason)
                    continue
                if status == "pending":
                    pending += 1
                relationship = {
                    **candidate,
                    "status": status,
                    "verification_reason": review_reason,
                    "passage_id": passage.passage_id,
                    "page": passage.page,
                    "start_offset": passage.start_offset,
                    "end_offset": passage.end_offset,
                }
                rel_identity = "|".join(
                    (
                        passage.passage_id,
                        self._normalize_match(candidate["subject"]),
                        candidate["relation"],
                        self._normalize_match(candidate["object"]),
                    )
                )
                relationship_records[hashlib.sha256(rel_identity.encode()).hexdigest()[:24]] = relationship

        if not passage_records:
            raise ValueError("No readable text found in the selected document pages.")
        if not relationship_records and not attempts:
            raise ValueError("Ollama returned no triples for the selected document pages.")

        all_surfaces = {
            surface
            for relationship in relationship_records.values()
            for surface in (relationship["subject"], relationship["object"])
        }
        canonical_by_surface, aliases_by_canonical = self._resolve_concepts(all_surfaces)
        relationships = []
        for identity, relationship in relationship_records.items():
            relationships.append(
                {
                    **relationship,
                    "id": identity,
                    "subject_canonical": canonical_by_surface[relationship["subject"]],
                    "object_canonical": canonical_by_surface[relationship["object"]],
                }
            )

        self._persist_evidence_graph(
            document_name,
            list(passage_records.values()),
            relationships,
            attempts,
            aliases_by_canonical,
        )
        return {
            "document_name": document_name,
            "passages": len(passage_records),
            "entities": len(aliases_by_canonical),
            "relationships": len(relationships),
            "verified": sum(item["status"] == "verified" for item in relationships),
            "pending": pending,
            "rejected": rejected,
            "graph": self.get_graph_data(document_name),
        }

    def create_evidence_graph_from_text(self, document_name: str, text: str) -> dict:
        passages = self._split_passage_text(text, document_name, None, 2400, 180)
        return self.create_evidence_graph(document_name, passages)

    @staticmethod
    def _attempt_record(
        attempt_id: str,
        document_name: str,
        passage: PassageChunk,
        status: str,
        reason: str,
        raw_candidate: object,
        validated: dict | None = None,
    ) -> dict:
        return {
            "id": attempt_id,
            "document_name": document_name,
            "passage_id": passage.passage_id,
            "status": status,
            "reason": reason,
            "raw_candidate": json.dumps(raw_candidate, ensure_ascii=False)[:4000],
            "confidence": validated.get("confidence") if validated else None,
        }

    def _persist_evidence_graph(
        self,
        document_name: str,
        passages: list[dict],
        relationships: list[dict],
        attempts: dict[str, dict],
        aliases_by_canonical: dict[str, set[str]],
    ) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MATCH (d:Document {name: $document_name})-[:HAS_PASSAGE]->(p:Passage)
                DETACH DELETE p
                """,
                document_name=document_name,
            )
            session.run(
                "MATCH (d:Document {name: $document_name}) DETACH DELETE d",
                document_name=document_name,
            )
            session.run(
                "MATCH ()-[r:RELATES {document_name: $document_name}]-() DELETE r",
                document_name=document_name,
            )
            session.run(
                "MATCH (a:ExtractionAttempt {document_name: $document_name}) DETACH DELETE a",
                document_name=document_name,
            )
            session.run(
                "MERGE (d:Document {name: $document_name}) SET d.pipeline = 'ollama-evidence-v1'",
                document_name=document_name,
            )
            session.run(
                """
                UNWIND $passages AS item
                MERGE (p:Passage {id: item.passage_id})
                SET p.page = item.page,
                    p.start_offset = item.start_offset,
                    p.end_offset = item.end_offset,
                    p.text = item.text,
                    p.document_name = $document_name
                WITH p
                MATCH (d:Document {name: $document_name})
                MERGE (d)-[:HAS_PASSAGE]->(p)
                """,
                document_name=document_name,
                passages=[
                    {
                        "passage_id": item["passage_id"],
                        "page": item["page"],
                        "start_offset": item["start_offset"],
                        "end_offset": item["end_offset"],
                        "text": item["text"],
                    }
                    for item in passages
                ],
            )
            session.run(
                """
                UNWIND $concepts AS item
                MERGE (c:Concept {canonical_name: item.canonical_name})
                ON CREATE SET c.aliases = item.aliases
                ON MATCH SET c.aliases = reduce(all_aliases = coalesce(c.aliases, []), alias IN item.aliases |
                    CASE WHEN alias IN all_aliases THEN all_aliases ELSE all_aliases + alias END)
                """,
                concepts=[
                    {"canonical_name": canonical, "aliases": sorted(aliases)}
                    for canonical, aliases in aliases_by_canonical.items()
                ],
            )
            session.run(
                """
                UNWIND $relationships AS item
                MATCH (p:Passage {id: item.passage_id})
                MATCH (subject:Concept {canonical_name: item.subject_canonical})
                MATCH (object:Concept {canonical_name: item.object_canonical})
                MERGE (p)-[:MENTIONS]->(subject)
                MERGE (p)-[:MENTIONS]->(object)
                MERGE (subject)-[r:RELATES {id: item.id}]->(object)
                SET r.document_name = $document_name,
                    r.relation = item.relation,
                    r.evidence = item.evidence,
                    r.passageId = item.passage_id,
                    r.page = item.page,
                    r.start_offset = item.start_offset,
                    r.end_offset = item.end_offset,
                    r.confidence = item.confidence,
                    r.status = item.status,
                    r.verification_reason = item.verification_reason,
                    r.model = $model
                """,
                document_name=document_name,
                model=self.model,
                relationships=relationships,
            )
            session.run(
                """
                UNWIND $attempts AS item
                MATCH (p:Passage {id: item.passage_id})
                MERGE (p)-[:HAS_EXTRACTION]->(a:ExtractionAttempt {id: item.id})
                SET a.document_name = item.document_name,
                    a.status = item.status,
                    a.reason = item.reason,
                    a.raw_candidate = item.raw_candidate,
                    a.confidence = item.confidence
                """,
                attempts=list(attempts.values()),
            )

    def get_graph_data(self, document_name: str | None = None):
        if document_name is None:
            return super().get_graph_data()

        with self.driver.session() as session:
            node_rows = [
                dict(record)
                for record in session.run(
                    """
                    MATCH (d:Document {name: $document_name})
                    OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                    OPTIONAL MATCH (p)-[:MENTIONS]->(c:Concept)
                    RETURN d.name AS document_name, p.id AS passage_id, p.page AS page,
                           p.start_offset AS start_offset, p.end_offset AS end_offset,
                           c.canonical_name AS concept_name
                    """,
                    document_name=document_name,
                )
            ]
            relationship_rows = [
                dict(record)
                for record in session.run(
                    """
                    MATCH (source:Concept)-[r:RELATES {document_name: $document_name}]->(target:Concept)
                    RETURN source.canonical_name AS source, target.canonical_name AS target,
                           r.relation AS relation, r.evidence AS evidence, r.passageId AS passage_id,
                           r.page AS page, r.confidence AS confidence, r.status AS status,
                           r.verification_reason AS verification_reason
                    """,
                    document_name=document_name,
                )
            ]

        nodes = []
        edges = []
        node_ids = set()
        edge_ids = set()
        document_id = f"document:{document_name}"
        if node_rows:
            nodes.append({"id": document_id, "label": document_name, "type": "Document"})
            node_ids.add(document_id)
        for row in node_rows:
            passage_id = row.get("passage_id")
            page = row.get("page")
            concept = row.get("concept_name")
            if passage_id:
                passage_node_id = f"passage:{passage_id}"
                if passage_node_id not in node_ids:
                    nodes.append({
                        "id": passage_node_id,
                        "label": f"Passage · p.{page}" if page else "Passage",
                        "type": "Passage",
                        "page": page,
                    })
                    node_ids.add(passage_node_id)
                edge = {"source": document_id, "target": passage_node_id, "label": f"PAGE {page}" if page else "HAS_PASSAGE"}
                edge_key = (edge["source"], edge["target"], edge["label"])
                if edge_key not in edge_ids:
                    edges.append(edge)
                    edge_ids.add(edge_key)
            if concept:
                concept_node_id = f"concept:{concept}"
                if concept_node_id not in node_ids:
                    nodes.append({"id": concept_node_id, "label": concept, "type": "Concept"})
                    node_ids.add(concept_node_id)
                if passage_id:
                    edge = {"source": f"passage:{passage_id}", "target": concept_node_id, "label": "MENTIONS"}
                    edge_key = (edge["source"], edge["target"], edge["label"])
                    if edge_key not in edge_ids:
                        edges.append(edge)
                        edge_ids.add(edge_key)
        for row in relationship_rows:
            source_id = f"concept:{row['source']}"
            target_id = f"concept:{row['target']}"
            for concept_id, name in ((source_id, row["source"]), (target_id, row["target"])):
                if concept_id not in node_ids:
                    nodes.append({"id": concept_id, "label": name, "type": "Concept"})
                    node_ids.add(concept_id)
            edge = {
                "source": source_id,
                "target": target_id,
                "label": row["relation"],
                "evidence": row["evidence"],
                "passageId": row["passage_id"],
                "page": row["page"],
                "confidence": row["confidence"],
                "status": row["status"],
                "verificationReason": row["verification_reason"],
            }
            edge_key = (edge["source"], edge["target"], edge["label"], edge["passageId"])
            if edge_key not in edge_ids:
                edges.append(edge)
                edge_ids.add(edge_key)

        nodes.sort(key=lambda node: {"Document": 0, "Concept": 1, "Passage": 2}.get(node["type"], 3))
        return {"nodes": nodes, "edges": edges}

    def get_graph_summary(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                WITH d, count(DISTINCT p) AS passage_count
                OPTIONAL MATCH (s:Concept)-[r:RELATES {document_name: d.name}]->(:Concept)
                RETURN d.name AS document_name, passage_count,
                       count(DISTINCT s) AS concept_count, count(DISTINCT r) AS relationship_count
                """
            )
            return [dict(record) for record in result]