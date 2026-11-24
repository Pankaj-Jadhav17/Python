from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.document_service import DocumentService
from app.services.question_service import QuestionService
from GraphRAG.graphiti_integration import GraphitiAdapter, get_shared_graphiti_adapter
from GraphRAG.retriever import GraphRAGRetriever, answer_question, answer_question_async


# 1. Production QuestionService uses Graphiti retrieval rather than automatically injecting GraphRAGStore
def test_production_question_service_uses_graphiti_retrieval(monkeypatch):
    class FakeAdapter(GraphitiAdapter):
        def __init__(self):
            super().__init__()
            self.invoked = False

        async def search_async(self, query, *, collection_id=None, limit=10):
            self.invoked = True
            return {
                "edges": [],
                "nodes": [],
                "episodes": [],
                "communities": [],
                "passages": [{"text": "Mitochondria produce ATP.", "document_name": "bio.pdf", "passage_id": "p1", "page": 2}],
            }

    fake_adapter = FakeAdapter()
    service = QuestionService(adapter=fake_adapter)

    monkeypatch.setattr("GraphRAG.retriever.generate_text", lambda *args, **kwargs: "Mitochondria generate ATP energy.")

    result = asyncio.run(service.ask_async("What produces ATP?", collection_id="biology"))
    assert fake_adapter.invoked is True
    assert result["answer"] == "Mitochondria generate ATP energy."
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "bio.pdf"


# 2. Explicit GraphRAGStore injection still works where supported
def test_explicit_graphragstore_injection_still_supported(monkeypatch):
    class CustomStore:
        def search_similar_passages(self, vector, limit, collection_id=None):
            return [{"text": "Chloroplasts perform photosynthesis.", "document_name": "plants.pdf", "passage_id": "pass-plant", "page": 5, "score": 0.99}]

        def expand_graph(self, evidence, depth, collection_id=None):
            return []

    monkeypatch.setattr("GraphRAG.retriever.embed_question", lambda q: [0.1, 0.2])
    monkeypatch.setattr("GraphRAG.retriever.generate_text", lambda *args, **kwargs: "Photosynthesis occurs in chloroplasts.")

    retriever = GraphRAGRetriever(store=CustomStore())
    result = asyncio.run(retriever.ask_async("Where does photosynthesis occur?", collection_id="botany"))

    assert result["answer"] == "Photosynthesis occurs in chloroplasts."
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "plants.pdf"
    assert result["evidence"][0]["page"] == 5


# 3. Hybrid search activates all intended search categories
# 4. Retrieval uses the correct collection/group ID
def test_hybrid_search_activates_all_categories_and_correct_group_id():
    calls = []

    class FakeGraphitiClient:
        def search_(self, query, group_ids=None, config=None, **kwargs):
            calls.append({"query": query, "group_ids": group_ids, "config": config})
            return SimpleNamespace(edges=[], nodes=[], episodes=[], communities=[])

    client = FakeGraphitiClient()
    adapter = GraphitiAdapter(graphiti=client)

    asyncio.run(adapter.search_async("quantum computing", collection_id="Physics 101", limit=12))

    assert len(calls) == 1
    call = calls[0]
    assert call["query"] == "quantum computing"
    # Collection normalization: "Physics 101" -> "physics_101"
    assert call["group_ids"] == ["physics_101"]

    config = call["config"]
    assert config is not None
    assert config.limit == 12
    # Check that all 4 search categories are active with RRF recipes
    assert hasattr(config, "edge_config") and config.edge_config is not None
    assert hasattr(config, "node_config") and config.node_config is not None
    assert hasattr(config, "episode_config") and config.episode_config is not None
    assert hasattr(config, "community_config") and config.community_config is not None


# 5. Search results preserve nodes, edges, episodes, and communities
# 6. Multiple supporting episodes are retained
def test_search_results_preserve_all_categories_and_multiple_supporting_episodes():
    fake_node = SimpleNamespace(uuid="node-1", name="Ribosome", labels=["BiologicalEntity"], summary="Synthesizes proteins.")
    fake_comm = SimpleNamespace(uuid="comm-1", name="Organelles", summary="Cell structures group.")
    fake_ep = SimpleNamespace(uuid="ep-1", name="bio#0", source_description="Document 'bio.txt' in collection 'bio'", content="Ribosomes synthesize proteins.")
    fake_edge = SimpleNamespace(
        uuid="edge-1",
        source_node_uuid="node-1",
        target_node_uuid="node-2",
        name="synthesizes",
        fact="Ribosome synthesizes protein",
        episodes=["ep-1", "ep-2", "ep-3"],  # Multiple supporting episodes!
        confidence=0.92,
        group_id="bio",
    )

    class FakeGraphitiClient:
        def search_(self, query, group_ids=None, config=None, **kwargs):
            return SimpleNamespace(
                edges=[fake_edge],
                edge_reranker_scores=[0.88],
                nodes=[fake_node],
                node_reranker_scores=[0.95],
                episodes=[fake_ep],
                episode_reranker_scores=[0.91],
                communities=[fake_comm],
                community_reranker_scores=[0.85],
            )

    adapter = GraphitiAdapter(graphiti=FakeGraphitiClient())
    # Stub _resolve_node_name for target_node_uuid
    adapter._resolve_node_name = lambda uuid: "Protein" if uuid == "node-2" else "Ribosome"

    results = asyncio.run(adapter.search_async("How do ribosomes work?", collection_id="bio"))

    # Preserves nodes
    assert len(results["nodes"]) == 1
    assert results["nodes"][0]["name"] == "Ribosome"
    assert results["nodes"][0]["score"] == 0.95

    # Preserves communities
    assert len(results["communities"]) == 1
    assert results["communities"][0]["name"] == "Organelles"
    assert results["communities"][0]["score"] == 0.85

    # Preserves episodes
    assert len(results["episodes"]) == 1
    assert results["episodes"][0]["uuid"] == "ep-1"
    assert results["episodes"][0]["score"] == 0.91

    # Preserves edges and multiple supporting episodes
    assert len(results["edges"]) == 1
    edge = results["edges"][0]
    assert edge["source"] == "Ribosome"
    assert edge["target"] == "Protein"
    assert edge["relation"] == "synthesizes"
    assert edge["score"] == 0.88
    # All 3 episodes are retained, NOT truncated to [0]
    assert edge["episodes"] == ["ep-1", "ep-2", "ep-3"]


# 7. Episode UUIDs correctly map to existing passage metadata
# 8. Original passage text reaches the answer-generation prompt
# 9. Source metadata is not fabricated (page None when unavailable)
def test_episode_uuid_maps_to_passage_and_reaches_prompt(monkeypatch):
    captured_prompt = {}

    def mock_generate_text(prompt, system_prompt=None, model=None, max_tokens=None):
        captured_prompt["prompt"] = prompt
        captured_prompt["system_prompt"] = system_prompt
        return "Answer based on verified passage text."

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_generate_text)

    class FakeAdapter(GraphitiAdapter):
        def __init__(self):
            super().__init__()

        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [
                    {
                        "source": "Enzyme",
                        "target": "Substrate",
                        "relation": "binds_to",
                        "evidence": "Enzyme binds to substrate at the active site.",
                        "episodes": ["ep-100"],
                    }
                ],
                "nodes": [{"id": "Enzyme", "name": "Enzyme", "label": "Enzyme", "type": "Concept"}],
                "episodes": [{"uuid": "ep-100", "content": "Original passage text from Biochemistry textbook."}],
                "communities": [{"name": "Catalysis", "summary": "Chemical reaction acceleration."}],
                "passages": [
                    {
                        "passage_id": "ep-100",
                        "document_id": "doc-biochem-42",
                        "document_name": "Biochemistry_Vol1.pdf",
                        "collection_id": "chemistry",
                        "chunk_index": 3,
                        "page": None,  # Genuine unavailable page
                        "text": "Original passage text from Biochemistry textbook.",
                    }
                ],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("How does an enzyme bind?", collection_id="chemistry"))

    assert result["answer"] == "Answer based on verified passage text."

    # 7. Episode UUID correctly mapped
    evidence = result["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["passage_id"] == "ep-100"
    assert evidence[0]["document_name"] == "Biochemistry_Vol1.pdf"
    assert evidence[0]["chunk_index"] == 3

    # 9. Source metadata is not fabricated: page is None
    assert evidence[0]["page"] is None

    # 8. Original passage text reaches the answer-generation prompt
    prompt = captured_prompt["prompt"]
    assert "Original passage text from Biochemistry textbook." in prompt
    assert "Biochemistry_Vol1.pdf" in prompt
    assert "Enzyme --[binds_to]--> Substrate" in prompt
    assert "Catalysis" in prompt


# 10. Async ingestion uses the shared adapter correctly
def test_async_ingestion_uses_shared_adapter(monkeypatch):
    from GraphRAG import ingest

    shared_adapter = get_shared_graphiti_adapter()
    called = {}

    async def fake_ingest_async(doc_name, text, *, collection_id=None, collection_name=None, document_id=None, store=None):
        called["doc_name"] = doc_name
        called["collection_id"] = collection_id
        return {"document_name": doc_name, "collection_id": collection_id, "reused": False, "passages": 1}

    monkeypatch.setattr(shared_adapter, "ingest_document_text_async", fake_ingest_async)

    result = asyncio.run(
        ingest.ingest_document_text_async("research.txt", "Scientific discovery text.", collection_id="science")
    )

    assert result["reused"] is False
    assert called["doc_name"] == "research.txt"
    assert called["collection_id"] == "science"


# 11. Page-range parameters are passed correctly
def test_page_range_parameters_passed_correctly(tmp_path, monkeypatch):
    import pymupdf
    from GraphRAG.ingest import ingest_file_async

    # Create dummy 3-page PDF
    pdf_path = tmp_path / "test_pages.pdf"
    doc = pymupdf.open()
    for i in range(1, 4):
        p = doc.new_page()
        p.insert_text((72, 72), f"Content on page {i}.")
    doc.save(str(pdf_path))
    doc.close()

    received_text = {}

    async def fake_ingest_text(doc_name, text, **kwargs):
        received_text["text"] = text
        return {"document_name": doc_name, "passages": 1}

    monkeypatch.setattr(get_shared_graphiti_adapter(), "ingest_document_text_async", fake_ingest_text)

    # Ingest only page 2
    asyncio.run(ingest_file_async(str(pdf_path), start_page=2, end_page=2, collection_id="test_col"))

    assert "Content on page 2." in received_text["text"]
    assert "Content on page 1." not in received_text["text"]
    assert "Content on page 3." not in received_text["text"]


# 12. The frontend/API evidence contract is correct
def test_api_evidence_contract():
    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [{"source": "A", "target": "B", "relation": "rel", "evidence": "A relates to B"}],
                "nodes": [{"id": "A", "label": "A", "type": "Concept"}, {"id": "B", "label": "B", "type": "Concept"}],
                "episodes": [],
                "communities": [],
                "passages": [
                    {
                        "passage_id": "pass-123",
                        "document_id": "doc-abc",
                        "document_name": "guide.pdf",
                        "collection_id": "docs",
                        "chunk_index": 0,
                        "page": 14,
                        "text": "A relates to B according to section 4.",
                        "score": 0.98,
                    }
                ],
            }

    with patch("GraphRAG.retriever.generate_text", return_value="Verified answer"):
        retriever = GraphRAGRetriever(adapter=FakeAdapter())
        response = asyncio.run(retriever.ask_async("Question about A and B", collection_id="docs"))

    # Check top-level contract keys expected by frontend and API consumers
    assert "answer" in response
    assert "path" in response
    assert "evidence" in response
    assert "nodes" in response
    assert "communities" in response

    # Check path contains nodes and edges for 3D visualization
    assert isinstance(response["path"]["nodes"], list)
    assert isinstance(response["path"]["edges"], list)

    # Check evidence contains original document passage metadata
    evidence_list = response["evidence"]
    assert len(evidence_list) == 1
    ev = evidence_list[0]
    assert ev["passage_id"] == "pass-123"
    assert ev["document_name"] == "guide.pdf"
    assert ev["page"] == 14
    assert ev["text"] == "A relates to B according to section 4."


# =====================================================================
# Specific Required Tests (Scenarios 1 through 8 from User Requirements)
# =====================================================================

# Test 1 — Retrieved episodes with an empty graph path
def test_scenario_1_retrieved_episodes_with_empty_graph_path(monkeypatch):
    """Graphiti returns relevant episodes but no edges or connected path.
    Expected: The existing LLM is invoked and generates an answer from the episode content."""
    captured = {}

    def mock_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "The plasma membrane is selectively permeable."

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_generate)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [
                    {
                        "uuid": "ep-cell-1",
                        "content": "The plasma membrane regulates molecular transport and is selectively permeable.",
                        "source_description": "Document 'biology.pdf' in collection 'bio'",
                    }
                ],
                "communities": [],
                "passages": [],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("How does the cell membrane work?", collection_id="bio"))

    assert result["answer"] == "The plasma membrane is selectively permeable."
    assert "selectively permeable" in captured["prompt"]
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "biology.pdf"
    assert result["path"]["edges"] == []
    assert result["path"]["nodes"] == []


# Test 2 — Retrieved episodes with supporting edges
def test_scenario_2_retrieved_episodes_with_supporting_edges(monkeypatch):
    """Graphiti returns passages and graph relationships.
    Expected: Answer generation works and source evidence is preserved."""
    monkeypatch.setattr("GraphRAG.retriever.generate_text", lambda *args, **kwargs: "Enzyme binds to substrate.")

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [
                    {
                        "source": "Enzyme",
                        "target": "Substrate",
                        "relation": "binds_to",
                        "evidence": "Enzymes bind substrates at active sites.",
                        "episodes": ["ep-enz"],
                    }
                ],
                "nodes": [{"id": "Enzyme", "name": "Enzyme", "type": "Concept"}, {"id": "Substrate", "name": "Substrate", "type": "Concept"}],
                "episodes": [],
                "communities": [],
                "passages": [
                    {
                        "passage_id": "ep-enz",
                        "document_name": "biochem.pdf",
                        "text": "Enzymes bind substrates at active sites.",
                        "page": 42,
                        "collection_id": collection_id,
                    }
                ],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("What does enzyme bind?", collection_id="biochem"))

    assert result["answer"] == "Enzyme binds to substrate."
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "biochem.pdf"
    assert result["evidence"][0]["page"] == 42
    assert len(result["path"]["edges"]) == 1
    assert result["path"]["edges"][0]["source"] == "Enzyme"
    assert result["path"]["edges"][0]["target"] == "Substrate"


# Test 3 — Episode-to-passage mapping
def test_scenario_3_episode_to_passage_mapping(monkeypatch):
    """Retrieved episode IDs correctly map to their original passage metadata.
    Expected: Original text and available document citations reach the LLM."""
    captured = {}

    def mock_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "Cell theory states that all living organisms are composed of cells."

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_generate)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [{"uuid": "ep-cell-theory", "content": "All organisms are composed of cells."}],
                "communities": [],
                "passages": [
                    {
                        "passage_id": "ep-cell-theory",
                        "document_id": "doc-bio-01",
                        "document_name": "Cell_Biology_Basics.pdf",
                        "collection_id": "biology",
                        "chunk_index": 2,
                        "page": 15,
                        "text": "All organisms are composed of cells, the basic unit of life.",
                    }
                ],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("What is cell theory?", collection_id="biology"))

    assert result["answer"] == "Cell theory states that all living organisms are composed of cells."
    assert "Cell_Biology_Basics.pdf" in captured["prompt"]
    assert "Page 15" in captured["prompt"]
    assert "All organisms are composed of cells" in captured["prompt"]
    assert result["evidence"][0]["passage_id"] == "ep-cell-theory"
    assert result["evidence"][0]["document_name"] == "Cell_Biology_Basics.pdf"
    assert result["evidence"][0]["page"] == 15


# Test 4 — Multiple relevant episodes
def test_scenario_4_multiple_relevant_episodes(monkeypatch):
    """Graphiti returns multiple supporting episodes.
    Expected: Relevant passages are available to the generation prompt."""
    captured = {}

    def mock_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "Mitochondria produce ATP through oxidative phosphorylation."

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_generate)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [
                    {
                        "uuid": "ep-1",
                        "content": "Mitochondria have double membranes.",
                        "source_description": "Document 'bio1.pdf'",
                    },
                    {
                        "uuid": "ep-2",
                        "content": "Cellular respiration produces ATP in the mitochondrial matrix.",
                        "source_description": "Document 'bio2.pdf'",
                    },
                    {
                        "uuid": "ep-3",
                        "content": "ATP is the energy currency of the cell.",
                        "source_description": "Document 'bio3.pdf'",
                    },
                ],
                "communities": [],
                "passages": [],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("How is energy generated in mitochondria?", collection_id="bio"))

    assert result["answer"] == "Mitochondria produce ATP through oxidative phosphorylation."
    assert len(result["evidence"]) == 3
    # Check all three distinct passages reached the prompt
    assert "Mitochondria have double membranes" in captured["prompt"]
    assert "Cellular respiration produces ATP" in captured["prompt"]
    assert "ATP is the energy currency" in captured["prompt"]


# Test 5 — No usable evidence
def test_scenario_5_no_usable_evidence(monkeypatch):
    """Graphiti returns no relevant episode or usable source passage.
    Expected: Existing no-evidence response is returned without an invented answer."""
    llm_called = False

    def mock_generate(*args, **kwargs):
        nonlocal llm_called
        llm_called = True
        return "Invented answer!"

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_generate)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [],
                "communities": [],
                "passages": [],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())
    result = asyncio.run(retriever.ask_async("What is quantum teleportation?", collection_id="bio"))

    assert llm_called is False
    assert result["answer"] == "I could not find enough verified evidence in the Graphiti knowledge graph to answer that question."
    assert result["path"]["nodes"] == []
    assert result["path"]["edges"] == []
    assert result["evidence"] == []


# Test 6 — Ollama generation failure
def test_scenario_6_ollama_generation_failure(monkeypatch):
    """Expected: The generation failure is identified separately from retrieval failure."""
    def mock_fail(*args, **kwargs):
        raise RuntimeError("Could not reach Ollama at http://localhost:11434: Connection refused")

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_fail)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [{"uuid": "ep-1", "content": "Valid retrieved evidence content."}],
                "communities": [],
                "passages": [],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())

    # Must raise the actual generation failure rather than silently swallowing it as "no evidence"
    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        asyncio.run(retriever.ask_async("Question with failing LLM", collection_id="bio"))


# Test 7 — Empty LLM output
def test_scenario_7_empty_llm_output(monkeypatch):
    """Expected: The application handles it safely and does not report a successful answer."""
    def mock_empty(*args, **kwargs):
        return "   "

    monkeypatch.setattr("GraphRAG.retriever.generate_text", mock_empty)

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            return {
                "edges": [],
                "nodes": [],
                "episodes": [{"uuid": "ep-1", "content": "Valid evidence."}],
                "communities": [],
                "passages": [],
            }

    retriever = GraphRAGRetriever(adapter=FakeAdapter())

    # Empty answer should raise RuntimeError and not report success
    with pytest.raises(RuntimeError, match="empty response"):
        asyncio.run(retriever.ask_async("Question with blank LLM response", collection_id="bio"))


# Test 8 — Collection isolation
def test_scenario_8_collection_isolation():
    """Expected: Only evidence belonging to the selected collection is used."""
    captured_calls = []

    class FakeAdapter(GraphitiAdapter):
        async def search_async(self, query, *, collection_id=None, limit=10):
            captured_calls.append({"query": query, "collection_id": collection_id})
            # Simulate returning evidence specifically tagged with the requested collection
            return {
                "edges": [],
                "nodes": [],
                "episodes": [],
                "communities": [],
                "passages": [
                    {
                        "passage_id": f"p-{collection_id}",
                        "document_name": f"{collection_id}_doc.pdf",
                        "collection_id": collection_id,
                        "text": f"Content specifically for collection {collection_id}",
                    }
                ],
            }

    with patch("GraphRAG.retriever.generate_text", return_value="Scoped answer"):
        retriever = GraphRAGRetriever(adapter=FakeAdapter())

        res1 = asyncio.run(retriever.ask_async("Query 1", collection_id="physics"))
        res2 = asyncio.run(retriever.ask_async("Query 2", collection_id="chemistry"))

    assert len(captured_calls) == 2
    assert captured_calls[0]["collection_id"] == "physics"
    assert captured_calls[1]["collection_id"] == "chemistry"

    assert res1["evidence"][0]["collection_id"] == "physics"
    assert res1["evidence"][0]["documentName"] == "physics_doc.pdf"

    assert res2["evidence"][0]["collection_id"] == "chemistry"
    assert res2["evidence"][0]["documentName"] == "chemistry_doc.pdf"
