from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from GraphRAG.db import GraphRAGStore
from GraphRAG.entity_resolution import (
    EntityResolver,
    check_type_compatibility,
    detect_graph_communities,
    normalize_entity_name,
)
from GraphRAG.extractor import (
    ALLOWED_ENTITY_TYPES,
    ALLOWED_RELATIONS,
    detect_negation,
    extract_triples,
    validate_entity_type,
    validate_extracted_triples,
)
from GraphRAG.graph_builder import build_graph_data
from GraphRAG.ingest import ingest_document_text, ingest_file
from GraphRAG.models.graph_models import CanonicalEntity, EntityMention, GraphEdge, GraphNode
from GraphRAG.retriever import answer_question


# 1. Structured extraction of multiple relationships from one chunk
def test_structured_extraction_multiple_relationships_from_one_chunk():
    text = "Mitochondria produce ATP and contain their own DNA."
    triples = extract_triples(text)
    assert len(triples) >= 2
    relations = {t["relation"] for t in triples}
    assert "produces" in relations or "contains" in relations
    assert all("evidence" in t and t["evidence"] for t in triples)


# 2. Independent validation of each relationship
def test_independent_validation_of_each_relationship():
    text = "Mitochondria produce ATP. Chloroplasts participate in photosynthesis."
    candidates = [
        # Valid candidate 1
        {
            "subject": "mitochondria",
            "relation": "produces",
            "object": "ATP",
            "evidence": "Mitochondria produce ATP.",
            "confidence": 0.95,
        },
        # Invalid candidate (invalid relation)
        {
            "subject": "mitochondria",
            "relation": "invented_relation_xyz",
            "object": "ATP",
            "evidence": "Mitochondria produce ATP.",
            "confidence": 0.9,
        },
        # Invalid candidate (evidence not in text)
        {
            "subject": "chloroplasts",
            "relation": "participates in",
            "object": "photosynthesis",
            "evidence": "Hallucinated evidence quote not found in source text.",
            "confidence": 0.9,
        },
        # Valid candidate 2
        {
            "subject": "chloroplasts",
            "relation": "participates in",
            "object": "photosynthesis",
            "evidence": "Chloroplasts participate in photosynthesis.",
            "confidence": 0.95,
        },
    ]

    validated = validate_extracted_triples(text, candidates)
    # Only the two valid ones should pass independently
    assert len(validated) == 2
    assert validated[0]["subject"] == "mitochondria"
    assert validated[1]["subject"] == "chloroplasts"


# 3. Reuse of a canonical entity across related documents
def test_reuse_of_canonical_entity_across_related_documents():
    resolver = EntityResolver(collection_id="cell_bio")
    # Document 1 mentions "Mitochondria"
    e1 = resolver.resolve_mention("Mitochondria", entity_type="BiologicalEntity")
    # Document 2 mentions "mitochondria" (lowercase)
    e2 = resolver.resolve_mention("mitochondria", entity_type="BiologicalEntity")
    # Document 3 mentions known alias "chondriosome"
    e3 = resolver.resolve_mention("chondriosome", entity_type="BiologicalEntity")

    assert e1.canonical_id == e2.canonical_id
    assert e1.canonical_id == e3.canonical_id
    assert e1.canonical_name == "Mitochondria"


# 4. Two distinct entities not being merged by clustering
def test_two_distinct_entities_not_merged_by_clustering():
    resolver = EntityResolver(collection_id="cell_bio")
    e1 = resolver.resolve_mention("RNA polymerase I", entity_type="BiologicalEntity")
    e2 = resolver.resolve_mention("RNA polymerase II", entity_type="BiologicalEntity")
    assert e1.canonical_id != e2.canonical_id
    assert e1.canonical_name != e2.canonical_name


# 5. Entity-type incompatibility preventing an invalid merge
def test_entity_type_incompatibility_prevents_invalid_merge():
    compat = check_type_compatibility("BiologicalEntity", "Organization")
    assert compat == 0.0

    resolver = EntityResolver(collection_id="general")
    e_bio = resolver.resolve_mention("Apple", entity_type="BiologicalEntity")
    e_org = resolver.resolve_mention("Apple", entity_type="Organization")
    assert e_bio.canonical_id != e_org.canonical_id


# 6. Shared canonical entities connecting valid subgraphs
def test_shared_canonical_entities_connecting_valid_subgraphs():
    # Doc A: Cell contains mitochondria
    # Doc B: Mitochondria participate in cellular respiration
    # Doc C: Cellular respiration produces ATP
    triples = [
        {
            "subject": "Cell",
            "subject_id": "c:bio:cell",
            "relation": "contains",
            "object": "Mitochondria",
            "object_id": "c:bio:mitochondria",
            "document_name": "DocA.pdf",
            "evidence": "Cells contain mitochondria.",
        },
        {
            "subject": "Mitochondria",
            "subject_id": "c:bio:mitochondria",
            "relation": "participates in",
            "object": "Cellular Respiration",
            "object_id": "c:bio:cellular_respiration",
            "document_name": "DocB.pdf",
            "evidence": "Mitochondria participate in cellular respiration.",
        },
        {
            "subject": "Cellular Respiration",
            "subject_id": "c:bio:cellular_respiration",
            "relation": "produces",
            "object": "ATP",
            "object_id": "c:bio:atp",
            "document_name": "DocC.pdf",
            "evidence": "Cellular respiration produces ATP.",
        },
    ]

    graph = build_graph_data(triples, collection_id="bio")
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "c:bio:cell" in node_ids
    assert "c:bio:mitochondria" in node_ids
    assert "c:bio:cellular_respiration" in node_ids
    assert "c:bio:atp" in node_ids

    # Mitochondria appears once as canonical node, referenced by both DocA and DocB
    mito_node = next(n for n in graph["nodes"] if n["id"] == "c:bio:mitochondria")
    assert set(mito_node["documents"]) == {"DocA.pdf", "DocB.pdf"}
    assert len(graph["edges"]) == 3


# 7. Unsupported edges not being generated from shared cluster membership
def test_unsupported_edges_not_generated_from_cluster_membership():
    triples = [
        {"subject": "Cell", "subject_id": "c:cell", "relation": "contains", "object": "Mitochondria", "object_id": "c:mito", "evidence": "ev1"},
        {"subject": "Mitochondria", "subject_id": "c:mito", "relation": "produces", "object": "ATP", "object_id": "c:atp", "evidence": "ev2"},
    ]
    graph = build_graph_data(triples)
    # Ensure there is NO fabricated direct Cell -> ATP edge
    cell_to_atp_edges = [
        e for e in graph["edges"]
        if e["source"] == "c:cell" and e["target"] == "c:atp"
    ]
    assert len(cell_to_atp_edges) == 0


# 8. Graph communities being stored separately from entity identity
def test_graph_communities_stored_separately_from_entity_identity():
    nodes = [
        {"id": "n1", "label": "Cell", "type": "Concept"},
        {"id": "n2", "label": "Mitochondria", "type": "Concept"},
        {"id": "n3", "label": "ATP", "type": "Concept"},
        {"id": "n4", "label": "Gradient Descent", "type": "Concept"},
        {"id": "n5", "label": "Learning Rate", "type": "Concept"},
    ]
    edges = [
        {"source": "n1", "target": "n2", "label": "contains"},
        {"source": "n2", "target": "n3", "label": "produces"},
        {"source": "n4", "target": "n5", "label": "requires"},
    ]
    communities = detect_graph_communities(nodes, edges)
    assert len(communities) == 5
    # Biology nodes should be in one community, ML nodes in another
    assert communities["n1"] == communities["n2"] == communities["n3"]
    assert communities["n4"] == communities["n5"]
    assert communities["n1"] != communities["n4"]
    # Node IDs remain unchanged
    assert "n1" in communities and "n4" in communities


# 9. Multiple passages supporting the same claim
def test_multiple_passages_supporting_the_same_claim():
    triples = [
        {
            "subject": "Mitochondria",
            "subject_id": "c:mito",
            "relation": "produces",
            "object": "ATP",
            "object_id": "c:atp",
            "document_name": "BioChapter1.pdf",
            "passage_id": "pass-1",
            "evidence": "Mitochondria produce ATP via respiration.",
            "confidence": 0.9,
        },
        {
            "subject": "Mitochondria",
            "subject_id": "c:mito",
            "relation": "produces",
            "object": "ATP",
            "object_id": "c:atp",
            "document_name": "BioChapter4.pdf",
            "passage_id": "pass-8",
            "evidence": "Mitochondria produce ATP during oxidative phosphorylation.",
            "confidence": 0.95,
        },
    ]

    graph = build_graph_data(triples)
    # Merges into single canonical edge with accumulated evidence
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert len(edge["evidence_records"]) == 2
    assert set(edge["document_names"]) == {"BioChapter1.pdf", "BioChapter4.pdf"}
    assert set(edge["passage_ids"]) == {"pass-1", "pass-8"}


# 10. Conflicting claims remaining distinguishable
def test_conflicting_claims_remaining_distinguishable():
    # If two documents assert different relations between same entities, both edges are preserved
    triples = [
        {"subject": "Drug X", "subject_id": "c:dx", "relation": "inhibits", "object": "Enzyme Y", "object_id": "c:ey", "evidence": "Drug X inhibits Enzyme Y.", "document_name": "StudyA.pdf"},
        {"subject": "Drug X", "subject_id": "c:dx", "relation": "supports", "object": "Enzyme Y", "object_id": "c:ey", "evidence": "Drug X supports Enzyme Y.", "document_name": "StudyB.pdf"},
    ]
    graph = build_graph_data(triples)
    assert len(graph["edges"]) == 2
    edge_labels = {e["label"] for e in graph["edges"]}
    assert edge_labels == {"inhibits", "supports"}


# 11. Evidence provenance surviving deduplication
def test_evidence_provenance_surviving_deduplication():
    triples = [
        {
            "subject": "Mitochondria",
            "subject_id": "c:mito",
            "relation": "produces",
            "object": "ATP",
            "object_id": "c:atp",
            "document_name": "Doc1.pdf",
            "passage_id": "p1",
            "page": 3,
            "evidence": "Quote 1 from doc 1.",
        },
        {
            "subject": "Mitochondria",
            "subject_id": "c:mito",
            "relation": "produces",
            "object": "ATP",
            "object_id": "c:atp",
            "document_name": "Doc2.pdf",
            "passage_id": "p2",
            "page": 12,
            "evidence": "Quote 2 from doc 2.",
        },
    ]
    graph = build_graph_data(triples)
    edge = graph["edges"][0]
    records = edge["evidence_records"]
    assert len(records) == 2
    assert records[0]["document_name"] == "Doc1.pdf"
    assert records[0]["page"] == 3
    assert records[1]["document_name"] == "Doc2.pdf"
    assert records[1]["page"] == 12


# 12. Duplicate ingestion being idempotent
def test_duplicate_ingestion_being_idempotent():
    class MockStore:
        def __init__(self):
            self.docs = {}

        def ensure_collection(self, col_id, name=None, description=None):
            return {"id": col_id, "name": name or col_id}

        def find_document_by_content_hash(self, content_hash, collection_id=None):
            if content_hash in self.docs:
                return self.docs[content_hash]
            return None

        def store_document_passages(self, doc_name, passages, **kwargs):
            self.docs[kwargs["content_hash"]] = {
                "document_id": kwargs["document_id"],
                "name": doc_name,
                "content_hash": kwargs["content_hash"],
                "status": "processed",
            }

        def get_canonical_entities(self, col_id):
            return []

        def store_entities_and_relationships(self, *args, **kwargs):
            pass

        def get_graph_data(self, **kwargs):
            return {"nodes": [{"id": "c:mito", "label": "Mitochondria", "type": "Concept"}], "edges": []}

    store = MockStore()
    text = "Mitochondria produce ATP."

    # First ingestion
    res1 = ingest_document_text("sample.txt", text, collection_id="col1", store=store)
    assert res1["reused"] is False

    # Second ingestion of unchanged content -> must reuse existing graph!
    res2 = ingest_document_text("sample.txt", text, collection_id="col1", store=store)
    assert res2["reused"] is True
    assert "Reused existing graph" in res2["message"]


# 13. Changed documents creating correct revisions
def test_changed_documents_create_correct_revisions():
    class MockStore:
        def __init__(self):
            self.hashes = set()

        def ensure_collection(self, *args, **kwargs):
            pass

        def find_document_by_content_hash(self, h, collection_id=None):
            return {"status": "processed"} if h in self.hashes else None

        def store_document_passages(self, doc_name, passages, **kwargs):
            self.hashes.add(kwargs["content_hash"])

        def get_canonical_entities(self, *args):
            return []

        def store_entities_and_relationships(self, *args, **kwargs):
            pass

        def get_graph_data(self, **kwargs):
            return {"nodes": [], "edges": []}

    store = MockStore()
    v1 = ingest_document_text("paper.pdf", "Mitochondria produce ATP.", collection_id="bio", store=store)
    assert v1["reused"] is False

    # Version 2 with modified text -> not reused, new hash processed
    v2 = ingest_document_text("paper.pdf", "Mitochondria produce ATP and contain DNA.", collection_id="bio", store=store)
    assert v2["reused"] is False


# 14. Collection boundaries being respected
def test_collection_boundaries_being_respected():
    resolver_bio = EntityResolver(collection_id="cell_biology")
    resolver_cs = EntityResolver(collection_id="computer_science")

    # "Tree" in biology vs "Tree" in computer science
    bio_tree = resolver_bio.resolve_mention("Tree", entity_type="BiologicalEntity")
    cs_tree = resolver_cs.resolve_mention("Tree", entity_type="Concept")

    assert bio_tree.collection_id == "cell_biology"
    assert cs_tree.collection_id == "computer_science"
    assert bio_tree.canonical_id != cs_tree.canonical_id


# 15. Individual-document graph retrieval remaining compatible
def test_individual_document_graph_retrieval_compatible():
    triples = [
        {"subject": "Cell", "subject_id": "c:cell", "relation": "contains", "object": "Mitochondria", "object_id": "c:mito", "document_name": "DocA.pdf", "evidence": "evA"},
        {"subject": "Mitochondria", "subject_id": "c:mito", "relation": "produces", "object": "ATP", "object_id": "c:atp", "document_name": "DocB.pdf", "evidence": "evB"},
    ]
    graph = build_graph_data(triples)
    doc_a_edges = [e for e in graph["edges"] if "DocA.pdf" in e["document_names"]]
    assert len(doc_a_edges) == 1
    assert doc_a_edges[0]["source"] == "c:cell"


# 16. Collection-level graph retrieval returning expected nodes and edges
def test_collection_level_graph_retrieval():
    triples = [
        {"subject": "Cell", "subject_id": "c:cell", "relation": "contains", "object": "Mitochondria", "object_id": "c:mito", "document_name": "DocA.pdf", "evidence": "evA"},
        {"subject": "Mitochondria", "subject_id": "c:mito", "relation": "produces", "object": "ATP", "object_id": "c:atp", "document_name": "DocB.pdf", "evidence": "evB"},
    ]
    collection_graph = build_graph_data(triples, collection_id="cell_bio")
    assert collection_graph["collection_id"] == "cell_bio"
    assert len(collection_graph["nodes"]) == 3
    assert len(collection_graph["edges"]) == 2


# 17. Existing question answering continuing to work
def test_existing_question_answering_continues_to_work(monkeypatch):
    class DummyStore:
        def search_similar_passages(self, vector, limit, collection_id=None):
            return [{
                "document_name": "Cell_Biology.pdf",
                "passage_id": "pass-1",
                "text": "Mitochondria produce ATP.",
                "page": 1,
                "score": 0.96,
            }]

        def expand_graph(self, evidence, depth, collection_id=None):
            return []

    monkeypatch.setattr("GraphRAG.retriever.embed_question", lambda q: [1.0, 0.0])
    monkeypatch.setattr(
        "GraphRAG.retriever.generate_text",
        lambda prompt, system_prompt, model, max_tokens: "Mitochondria produce ATP in the cell.",
    )

    result = answer_question("What do mitochondria produce?", collection_id="cell_bio", store=DummyStore())
    assert result["answer"] == "Mitochondria produce ATP in the cell."
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "Cell_Biology.pdf"


def test_document_identity_and_collection_scope_are_safe():
    class FakeResult:
        def __init__(self, rows=None):
            self.rows = rows or []

        def __iter__(self):
            return iter(self.rows)

        def single(self):
            return self.rows[0] if self.rows else None

    class FakeSession:
        def __init__(self):
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, **kwargs):
            self.queries.append((query, kwargs))
            if "MERGE (d:Document {name: $document_name})" in query:
                raise AssertionError("Document identity must use stable document_id instead of the filename.")
            if "MATCH (c:Concept)" in query and "OR c.collection_id IS NULL" in query:
                raise AssertionError("Legacy NULL collection entries must not leak into a collection-scoped query.")
            return FakeResult([])

    class FakeDriver:
        def __init__(self):
            self.session_obj = FakeSession()

        def session(self):
            return self.session_obj

    store = GraphRAGStore.__new__(GraphRAGStore)
    store.config = SimpleNamespace()
    store.config.neo4j_uri = "bolt://example"
    store.config.neo4j_user = "neo4j"
    store.config.neo4j_password = "secret"
    store.driver = FakeDriver()

    store.store_document_passages(
        "example.pdf",
        [{
            "passage_id": "p-1",
            "document_id": "doc-123",
            "document_name": "example.pdf",
            "collection_id": "bio",
            "chunk_index": 0,
            "page": 1,
            "start_offset": 0,
            "end_offset": 30,
            "text": "Mitochondria produce ATP.",
            "content_hash": "hash-1",
            "embedding": [0.1, 0.2],
        }],
        document_id="doc-123",
        collection_id="bio",
        content_hash="hash-1",
    )

    store.get_canonical_entities(collection_id="bio")
