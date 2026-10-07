import re
from collections.abc import Iterable
from itertools import chain

from neo4j import GraphDatabase

from app.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

BIOLOGY_TERMS = (
    "sexual reproduction", "flowering plants", "angiosperms", "flower", "inflorescence",
    "stamen", "filament", "anther", "microsporangium", "sporogenous tissue",
    "microsporogenesis", "pollen mother cell", "microspore tetrad", "microspore",
    "pollen grain", "male gametophyte", "pollen tube", "male gamete", "gynoecium",
    "pistil", "ovule", "megasporangium", "megaspore mother cell", "megasporogenesis",
    "megaspore", "embryo sac", "female gametophyte", "synergid", "polar nuclei",
    "double fertilisation", "syngamy", "triple fusion", "primary endosperm cell",
    "endosperm", "zygote", "embryo", "seed", "fruit", "ovary", "pollination",
    "self-pollination", "cross-pollination", "self-incompatibility", "apomixis",
    "polyembryony",
)
BIOLOGY_DOCUMENT_MARKERS = ("sexual reproduction", "flowering plants", "angiosperm", "microspore")


class PDFGraphService:
    """Extract text from PDF files and create a Neo4j knowledge graph."""

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self.uri = uri or NEO4J_URI or "bolt://localhost:7687"
        self.user = user or NEO4J_USER or "neo4j"
        self.password = password or NEO4J_PASSWORD or "your_neo4j_password"
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def extract_text_from_pdf(self, file_path: str) -> str:
        return "\n".join(self.iter_text_chunks(file_path, ".pdf")).strip()

    def iter_text_chunks(
        self,
        file_path: str,
        extension: str,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> Iterable[str]:
        """Yield extracted text incrementally rather than joining the whole document."""
        if extension == ".pdf":
            try:
                import pymupdf

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
                        if text.strip():
                            yield text
            except ValueError:
                raise
            except Exception as error:
                raise ValueError(f"Could not parse this PDF with PyMuPDF: {error}") from error
            return

        if extension == ".docx":
            try:
                from docx import Document

                document = Document(file_path)
                for paragraph in document.paragraphs:
                    if paragraph.text.strip():
                        yield paragraph.text
            except Exception as error:
                raise ValueError("Could not read this DOCX file. Check that it is a valid Word document.") from error
            return

        if extension == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="replace") as text_file:
                carry = ""
                while chunk := text_file.read(64 * 1024):
                    combined = carry + chunk
                    yield combined
                    carry = combined[-512:]
            return

        raise ValueError(f"Unsupported document type: {extension}")

    def extract_entities_and_relationships(self, text: str, biology_mode: bool | None = None):
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return [], []

        entities = []
        relationships = []
        lowered_text = normalized.lower()
        is_biology_text = biology_mode if biology_mode is not None else any(
            marker in lowered_text for marker in BIOLOGY_DOCUMENT_MARKERS
        )
        known_terms = list(BIOLOGY_TERMS) if is_biology_text else [
            "machine learning", "deep learning", "data science", "healthcare",
            "cancer detection", "neural networks", "natural language processing",
            "ai", "rag", "neo4j", "graph database", "pdf",
        ]
        for term in known_terms:
            if term in lowered_text:
                entities.append(term)

        for sentence in re.split(r"(?<=[.!?])\s+", normalized):
            sentence_lower = sentence.lower()
            if not is_biology_text:
                if "machine learning" in sentence_lower and "healthcare" in sentence_lower:
                    relationships.append(("machine learning", "helps", "healthcare"))
                if "deep learning" in sentence_lower and "cancer detection" in sentence_lower:
                    relationships.append(("deep learning", "used in", "cancer detection"))
                if "data science" in sentence_lower and "healthcare" in sentence_lower:
                    relationships.append(("data science", "works with", "healthcare"))
                if "ai" in sentence_lower and "rag" in sentence_lower:
                    relationships.append(("ai", "uses", "rag"))
                if "neo4j" in sentence_lower and "graph database" in sentence_lower:
                    relationships.append(("neo4j", "stores", "graph database"))
            if "microsporangium" in sentence_lower and "sporogenous tissue" in sentence_lower:
                relationships.append(("microsporangium", "contains", "sporogenous tissue"))
            if "sporogenous tissue" in sentence_lower and "microspore tetrad" in sentence_lower:
                relationships.append(("sporogenous tissue", "forms", "microspore tetrad"))
            if "pollen mother cell" in sentence_lower and "microspore" in sentence_lower:
                relationships.append(("pollen mother cell", "produces", "microspore"))
            if "microspore" in sentence_lower and "pollen grain" in sentence_lower:
                relationships.append(("microspore", "develops into", "pollen grain"))
            if "ovule" in sentence_lower and "embryo sac" in sentence_lower:
                relationships.append(("ovule", "contains", "embryo sac"))
            if "megaspore mother cell" in sentence_lower and "megaspore" in sentence_lower:
                relationships.append(("megaspore mother cell", "produces", "megaspore"))
            if "megaspore" in sentence_lower and "embryo sac" in sentence_lower:
                relationships.append(("megaspore", "develops into", "embryo sac"))
            if "pollen tube" in sentence_lower and "male gamete" in sentence_lower:
                relationships.append(("pollen tube", "releases", "male gamete"))
            if "triple fusion" in sentence_lower and "primary endosperm cell" in sentence_lower:
                relationships.append(("triple fusion", "forms", "primary endosperm cell"))
            if "primary endosperm cell" in sentence_lower and "endosperm" in sentence_lower:
                relationships.append(("primary endosperm cell", "develops into", "endosperm"))
            if "zygote" in sentence_lower and "embryo" in sentence_lower:
                relationships.append(("zygote", "develops into", "embryo"))
            if "ovule" in sentence_lower and "seed" in sentence_lower:
                relationships.append(("ovule", "develops into", "seed"))
            if "ovary" in sentence_lower and "fruit" in sentence_lower:
                relationships.append(("ovary", "develops into", "fruit"))
            if "apomixis" in sentence_lower and "seed" in sentence_lower:
                relationships.append(("apomixis", "produces without fertilisation", "seed"))
            if "flower" in sentence_lower and "sexual reproduction" in sentence_lower:
                relationships.append(("flower", "is the site of", "sexual reproduction"))

        extra_entities = [] if is_biology_text else re.findall(
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
            normalized,
        )
        known_entity_names = {entity.lower() for entity in entities}
        for candidate in extra_entities:
            cleaned = re.sub(r"\s+", " ", candidate).strip()
            if len(cleaned) >= 3 and cleaned.lower() not in {"the", "and", "for", "with", "that", "this"}:
                if cleaned.lower() not in known_entity_names:
                    entities.append(cleaned)
                    known_entity_names.add(cleaned.lower())

        return entities, list(dict.fromkeys(relationships))

    def create_graph_from_chunks(self, document_name: str, chunks: Iterable[str]):
        entities = {}
        relationships = {}
        has_text = False
        chunk_iterator = iter(chunks)
        first_chunk = next(chunk_iterator, "")
        first_content = f"{document_name} {first_chunk}".lower()
        biology_mode = any(marker in first_content for marker in BIOLOGY_DOCUMENT_MARKERS)
        for chunk in chain((first_chunk,), chunk_iterator):
            has_text = has_text or bool(chunk.strip())
            chunk_entities, chunk_relationships = self.extract_entities_and_relationships(chunk, biology_mode)
            entities.update((entity.lower(), entity) for entity in chunk_entities)
            relationships.update(
                ((source.lower(), relation.lower(), target.lower()), (source, relation, target))
                for source, relation, target in chunk_relationships
            )
        if not has_text:
            raise ValueError("No readable text found in the document.")
        return self._persist_graph(document_name, list(entities.values()), list(relationships.values()))

    def create_graph(self, document_name: str, text: str):
        entities, relationships = self.extract_entities_and_relationships(text)
        return self._persist_graph(document_name, entities, relationships)

    def _persist_graph(self, document_name: str, entities: list[str], relationships: list[tuple[str, str, str]]):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (doc:Document {name: $document_name})
                OPTIONAL MATCH (doc)-[contains:CONTAINS]->()
                WITH doc, collect(contains) AS old_contains
                FOREACH (link IN old_contains | DELETE link)
                WITH doc
                OPTIONAL MATCH ()-[old_relationship:RELATED_TO {document_name: $document_name}]->()
                WITH doc, collect(old_relationship) AS old_relationships
                FOREACH (relationship IN old_relationships | DELETE relationship)
                DELETE doc
                """,
                document_name=document_name,
            )
            session.run("MERGE (d:Document {name: $document_name})", document_name=document_name)
            session.run("UNWIND $entities AS name MERGE (:Entity {name: name})", entities=entities)
            session.run(
                """
                UNWIND $relationships AS item
                MATCH (source:Entity {name: item.source})
                MATCH (target:Entity {name: item.target})
                MERGE (source)-[:RELATED_TO {type: item.type, document_name: $document_name}]->(target)
                """,
                document_name=document_name,
                relationships=[
                    {"source": source, "type": relation, "target": target}
                    for source, relation, target in relationships
                ],
            )
            session.run(
                """
                MATCH (doc:Document {name: $document_name})
                UNWIND $entities AS name
                MATCH (entity:Entity {name: name})
                MERGE (doc)-[:CONTAINS]->(entity)
                """,
                document_name=document_name,
                entities=entities,
            )

        return {
            "document_name": document_name,
            "entities": len(entities),
            "relationships": len(relationships),
            "graph": self.get_graph_data(document_name),
        }

    def get_graph_data(self, document_name: str | None = None):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)-[contains:CONTAINS]->(e:Entity)
                WHERE $document_name IS NULL OR d.name = $document_name
                OPTIONAL MATCH (e)-[r]->(other:Entity)
                WHERE $document_name IS NULL OR r.document_name = $document_name OR r IS NULL
                RETURN d.name AS document_name, e.name AS entity_name,
                       type(contains) AS document_relationship,
                      r.type AS relationship_type, other.name AS related_entity
                """,
                document_name=document_name,
            )
            rows = [dict(record) for record in result]

        nodes = []
        edges = []
        seen_nodes = set()
        seen_edges = set()

        for row in rows:
            doc_name = row.get("document_name")
            entity_name = row.get("entity_name")
            related_entity = row.get("related_entity")
            relationship_type = row.get("relationship_type")
            document_relationship = row.get("document_relationship")

            if entity_name and entity_name not in seen_nodes:
                nodes.append({"id": entity_name, "label": entity_name, "type": "Entity"})
                seen_nodes.add(entity_name)
            if related_entity and related_entity not in seen_nodes:
                nodes.append({"id": related_entity, "label": related_entity, "type": "Entity"})
                seen_nodes.add(related_entity)
            if doc_name and doc_name not in seen_nodes:
                nodes.append({"id": doc_name, "label": doc_name, "type": "Document"})
                seen_nodes.add(doc_name)
            if doc_name and entity_name and document_relationship:
                edge_key = (doc_name, entity_name, document_relationship)
                if edge_key not in seen_edges:
                    edges.append({"source": doc_name, "target": entity_name, "label": document_relationship})
                    seen_edges.add(edge_key)
            if entity_name and related_entity and relationship_type:
                edge_key = (entity_name, related_entity, relationship_type)
                if edge_key not in seen_edges:
                    edges.append({"source": entity_name, "target": related_entity, "label": relationship_type})
                    seen_edges.add(edge_key)

        return {"nodes": nodes, "edges": edges}

    def get_graph_summary(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)-[:CONTAINS]->(e:Entity)
                OPTIONAL MATCH (e)-[r]->(other:Entity)
                RETURN d.name AS document_name, count(DISTINCT e) AS entity_count, count(DISTINCT r) AS relationship_count
                """
            )
            rows = [dict(record) for record in result]
        return rows

    def close(self):
        self.driver.close()
