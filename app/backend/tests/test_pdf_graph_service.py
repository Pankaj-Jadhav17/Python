import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.routers import documents
from app.services.evidence_graph_service import EvidenceGraphService, PassageChunk
from app.services.pdf_graph_service import PDFGraphService


def test_extract_entities_and_relationships_from_pdf_text():
    text = """
    Machine learning helps healthcare systems. 
    Deep learning is used in cancer detection. 
    Data science works with healthcare and machine learning.
    """

    service = PDFGraphService()
    entities, relationships = service.extract_entities_and_relationships(text)

    assert len(entities) >= 3
    assert any("machine learning" in entity.lower() for entity in entities)
    assert len(relationships) >= 1


def test_extract_biology_entities_and_chapter_relationships():
    service = PDFGraphService()
    text = (
        "A microspore develops into a pollen grain. "
        "As ovules mature into seeds, the ovary develops into a fruit. "
        "Triple fusion forms the primary endosperm cell, which develops into endosperm. "
        "Panchanan Maheshwari studied these processes, and AI systems use RAG."
    )

    entities, relationships = service.extract_entities_and_relationships(text)

    assert {"microspore", "pollen grain", "ovule", "seed", "ovary", "fruit"}.issubset(
        {entity.lower() for entity in entities}
    )
    assert ("ovule", "develops into", "seed") in relationships
    assert ("ovary", "develops into", "fruit") in relationships
    assert ("triple fusion", "forms", "primary endosperm cell") in relationships
    assert not any(source == "ai" for source, _, _ in relationships)

    front_matter_entities, _ = service.extract_entities_and_relationships(
        "Panchanan Maheshwari studied plants.", biology_mode=True
    )
    assert front_matter_entities == []


def test_relationships_are_scoped_to_the_document():
    service = PDFGraphService()
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, query: str, **parameters):
            calls.append((query, parameters))
            return []

    class Driver:
        def session(self):
            return Session()

    service.driver = Driver()
    service._persist_graph("chapter.pdf", ["ovule", "seed"], [("ovule", "develops into", "seed")])

    relationship_query, relationship_parameters = next(
        (query, parameters) for query, parameters in calls if "RELATED_TO" in query
    )
    graph_query, _ = next(
        (query, parameters) for query, parameters in calls if "OPTIONAL MATCH (e)-[r]" in query
    )
    assert "document_name: $document_name" in relationship_query
    assert relationship_parameters["document_name"] == "chapter.pdf"
    assert "r.document_name = $document_name OR r IS NULL" in graph_query
    assert any("DELETE doc" in query and "old_contains" in query for query, _ in calls)


def test_graph_data_deduplicates_document_edges():
    service = PDFGraphService()
    duplicate_rows = [
        {
            "document_name": "chapter.pdf",
            "entity_name": "ovule",
            "related_entity": "seed",
            "relationship_type": "develops into",
            "document_relationship": "CONTAINS",
        },
        {
            "document_name": "chapter.pdf",
            "entity_name": "ovule",
            "related_entity": "zygote",
            "relationship_type": "develops into",
            "document_relationship": "CONTAINS",
        },
    ]

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, *_args, **_kwargs):
            return duplicate_rows

    class Driver:
        def session(self):
            return Session()

    service.driver = Driver()

    graph = service.get_graph_data("chapter.pdf")

    assert graph["edges"].count({"source": "chapter.pdf", "target": "ovule", "label": "CONTAINS"}) == 1
    assert len(graph["edges"]) == 3


def test_text_file_is_read_in_overlapping_chunks(tmp_path: Path):
    service = PDFGraphService()
    file_path = tmp_path / "large.txt"
    file_path.write_text("x" * (64 * 1024 - 10) + "Machine learning helps healthcare.", encoding="utf-8")

    chunks = list(service.iter_text_chunks(str(file_path), ".txt"))
    relationships = [
        relationship
        for chunk in chunks
        for relationship in service.extract_entities_and_relationships(chunk)[1]
    ]

    assert ("machine learning", "helps", "healthcare") in relationships


def test_pdf_extraction_can_select_a_page_range(tmp_path: Path):
    pymupdf = pytest.importorskip("pymupdf")
    service = PDFGraphService()
    file_path = tmp_path / "chapters.pdf"
    document = pymupdf.open()
    for page_text in ("Front matter", "Chapter one text", "Chapter two text"):
        page = document.new_page()
        page.insert_text((72, 72), page_text)
    document.save(file_path)
    document.close()

    chunks = list(service.iter_text_chunks(str(file_path), ".pdf", start_page=2, end_page=2))

    assert chunks == ["Chapter one text"]


def test_docx_text_is_extracted(tmp_path: Path):
    docx = pytest.importorskip("docx")
    service = PDFGraphService()
    file_path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("Machine learning helps healthcare.")
    document.save(file_path)

    chunks = list(service.iter_text_chunks(str(file_path), ".docx"))

    assert chunks == ["Machine learning helps healthcare."]


def test_upload_streams_large_file_and_returns_graph(monkeypatch: pytest.MonkeyPatch):
    content = b"Machine learning helps healthcare. " * 40_000
    observed = {}

    class StubService:
        def check_ollama(self):
            observed["ollama_checked"] = True

        def iter_passages(
            self,
            file_path: str,
            extension: str,
            document_name: str,
            start_page: int | None = None,
            end_page: int | None = None,
        ):
            observed["extension"] = extension
            observed["document_name"] = document_name
            observed["page_range"] = (start_page, end_page)
            observed["uploaded_bytes"] = Path(file_path).read_bytes()
            observed["temporary_path"] = Path(file_path)
            return iter([PassageChunk("passage-id", None, 0, 36, "Machine learning helps healthcare.")])

        def create_evidence_graph(self, document_name: str, passages):
            observed["chunks"] = list(passages)
            return {
                "document_name": document_name,
                "entities": 2,
                "relationships": 1,
                "graph": {"nodes": [], "edges": []},
            }

    monkeypatch.setattr(documents, "service", StubService())
    uploaded_file = UploadFile(filename="large.txt", file=BytesIO(content))

    result = asyncio.run(documents.upload_document(uploaded_file))

    assert observed["extension"] == ".txt"
    assert observed["ollama_checked"]
    assert observed["document_name"] == "large.txt"
    assert observed["page_range"] == (None, None)
    assert observed["uploaded_bytes"] == content
    assert not observed["temporary_path"].exists()
    assert result["entities"] == 2
    assert result["message"].startswith("Document passages and evidence graph")


def test_passage_chunks_keep_pdf_page_and_offsets(tmp_path: Path):
    pymupdf = pytest.importorskip("pymupdf")
    service = EvidenceGraphService()
    pdf_path = tmp_path / "passages.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Flowering plants reproduce sexually. Pollen grains carry male gametes.")
    document.save(pdf_path)
    document.close()

    passages = list(service.iter_passages(str(pdf_path), ".pdf", "chapter.pdf", max_chars=45, overlap=5))

    assert len(passages) > 1
    assert all(passage.page == 1 for passage in passages)
    assert all(passage.start_offset < passage.end_offset for passage in passages)
    assert all(passage.passage_id for passage in passages)


def test_candidate_validation_requires_allowed_relation_and_verbatim_evidence():
    service = EvidenceGraphService()
    passage = PassageChunk("p1", 7, 0, 70, "Microspores develop into pollen grains.")
    valid = {
        "subject": "Microspores",
        "relation": "develops into",
        "object": "pollen grains",
        "evidence": "Microspores develop into pollen grains.",
        "confidence": 0.88,
    }

    candidate, reason = service.validate_candidate(passage, valid)
    assert reason is None
    assert candidate is not None
    assert candidate["relation"] == "develops into"

    invalid_relation = {**valid, "relation": "causes"}
    assert service.validate_candidate(passage, invalid_relation)[1] == "relation is not allowed: causes"

    invalid_evidence = {**valid, "evidence": "Pollen grains are produced by anthers."}
    assert service.validate_candidate(passage, invalid_evidence)[1] == "evidence quote does not occur in the passage"

    missing_object = {**valid, "object": "embryo sac"}
    assert service.validate_candidate(passage, missing_object)[1] == "object does not occur in the evidence quote"


def test_ollama_request_uses_schema_and_token_cap(monkeypatch: pytest.MonkeyPatch):
    service = EvidenceGraphService(model="llama3.2:latest")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"message":{"content":"{\\"triples\\":[]}"}}'

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.services.evidence_graph_service.urllib.request.urlopen", fake_urlopen)

    result = service._call_ollama("system", "user", {"type": "object"})

    assert result == {"triples": []}
    assert captured["payload"]["format"] == {"type": "object"}
    assert captured["payload"]["options"]["num_predict"] == 384
    assert captured["payload"]["options"]["temperature"] == 0


def test_low_confidence_candidate_is_reviewed_and_attempts_are_persisted(monkeypatch: pytest.MonkeyPatch):
    service = EvidenceGraphService(confidence_threshold=0.72)
    passage = PassageChunk("passage-1", 9, 120, 168, "Pollen grains form male gametes.")
    candidates = [
        {
            "subject": "Pollen grains",
            "relation": "forms",
            "object": "male gametes",
            "evidence": "Pollen grains form male gametes.",
            "confidence": 0.61,
        },
        {
            "subject": "Pollen grains",
            "relation": "develops into",
            "object": "zygote",
            "evidence": "Pollen grains form male gametes.",
            "confidence": 0.96,
        },
    ]
    reviewed = []
    persisted = {}
    monkeypatch.setattr(service, "extract_candidates", lambda _passage: candidates)

    def review(_passage, candidate):
        reviewed.append(candidate)
        return {"decision": "verified", "reason": "The quote directly supports the triple."}

    monkeypatch.setattr(service, "review_candidate", review)
    monkeypatch.setattr(
        service,
        "_resolve_concepts",
        lambda concepts: (
            {concept: concept.casefold() for concept in concepts},
            {concept.casefold(): {concept} for concept in concepts},
        ),
    )

    def persist(_document_name, passages, relationships, attempts, _aliases):
        persisted.update(passages=passages, relationships=relationships, attempts=attempts)

    monkeypatch.setattr(service, "_persist_evidence_graph", persist)
    monkeypatch.setattr(service, "get_graph_data", lambda _document_name: {"nodes": [], "edges": []})

    result = service.create_evidence_graph("biology.pdf", [passage])

    assert len(reviewed) == 1
    assert result["verified"] == 1
    assert result["rejected"] == 1
    assert persisted["passages"][0]["page"] == 9
    assert persisted["passages"][0]["start_offset"] == 120
    assert persisted["relationships"][0]["status"] == "verified"
    assert persisted["relationships"][0]["evidence"] == "Pollen grains form male gametes."
    assert persisted["relationships"][0]["passage_id"] == "passage-1"
    assert any(attempt["status"] == "rejected" for attempt in persisted["attempts"].values())


def test_evidence_graph_persistence_stores_required_provenance():
    service = EvidenceGraphService(model="llama3.2:latest")
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, query: str, **parameters):
            calls.append((query, parameters))
            return []

    class Driver:
        def session(self):
            return Session()

    service.driver = Driver()
    passage = {
        "passage_id": "p1",
        "page": 7,
        "start_offset": 10,
        "end_offset": 60,
        "text": "Microspores develop into pollen grains.",
    }
    relationship = {
        "id": "r1",
        "passage_id": "p1",
        "page": 7,
        "start_offset": 10,
        "end_offset": 48,
        "subject_canonical": "microspore",
        "object_canonical": "pollen grain",
        "relation": "develops into",
        "evidence": "Microspores develop into pollen grains.",
        "confidence": 0.91,
        "status": "verified",
        "verification_reason": "confidence met threshold",
    }
    attempt = {"id": "a1", "passage_id": "p1", "document_name": "chapter.pdf", "status": "rejected"}

    service._persist_evidence_graph(
        "chapter.pdf",
        [passage],
        [relationship],
        {"a1": attempt},
        {"microspore": {"microspore"}, "pollen grain": {"pollen grains"}},
    )

    passage_query, passage_parameters = next((q, p) for q, p in calls if "MERGE (p:Passage" in q)
    relates_query, relates_parameters = next((q, p) for q, p in calls if "UNWIND $relationships AS item" in q)
    attempt_query, attempt_parameters = next((q, p) for q, p in calls if "UNWIND $attempts AS item" in q)
    assert "p.page = item.page" in passage_query
    assert "p.start_offset = item.start_offset" in passage_query
    assert passage_parameters["passages"][0]["passage_id"] == "p1"
    assert "r.evidence = item.evidence" in relates_query
    assert "r.passageId = item.passage_id" in relates_query
    assert "r.status = item.status" in relates_query
    assert relates_parameters["relationships"][0]["confidence"] == 0.91
    assert "HAS_EXTRACTION" in attempt_query
    assert attempt_parameters["attempts"][0]["status"] == "rejected"
