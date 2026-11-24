import asyncio

from GraphRAG.retriever import answer_question


def test_retriever_returns_answer_and_evidence(monkeypatch):
    class DummyStore:
        def search_similar_passages(self, question_vector, limit):
            assert limit > 0
            return [
                {
                    "document_name": "biology.pdf",
                    "passage_id": "passage-1",
                    "text": "Microspore develops into pollen grain.",
                    "page": 1,
                    "score": 0.95,
                }
            ]

        def expand_graph(self, evidence, depth):
            assert depth > 0
            return []

    monkeypatch.setattr("GraphRAG.retriever.embed_question", lambda question: [1.0, 0.0])
    monkeypatch.setattr(
        "GraphRAG.retriever.generate_text",
        lambda prompt, system_prompt, model, max_tokens: "A microspore develops into a pollen grain.",
    )

    result = answer_question("What develops from a microspore?", store=DummyStore())

    assert result["answer"] == "A microspore develops into a pollen grain."
    assert result["path"]["edges"]
    assert result["evidence"][0]["documentName"] == "biology.pdf"


def test_production_question_service_uses_graphiti_retrieval_without_graphragstore(monkeypatch):
    """Production QuestionService must use Graphiti retrieval and must NOT inject GraphRAGStore."""
    from app.services.question_service import QuestionService
    from GraphRAG.graphiti_integration import GraphitiAdapter

    class FakeAdapter(GraphitiAdapter):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def search_async(self, query, *, collection_id=None, limit=10):
            self.calls.append({"query": query, "collection_id": collection_id, "limit": limit})
            return {
                "edges": [],
                "nodes": [],
                "episodes": [],
                "communities": [],
                "passages": [
                    {
                        "passage_id": "pass-1",
                        "document_name": "cell.txt",
                        "text": "A cell is the basic structural and functional unit of life.",
                        "page": None,
                        "collection_id": collection_id,
                    }
                ],
            }

    fake_adapter = FakeAdapter()
    service = QuestionService(adapter=fake_adapter)

    # Verify no GraphRAGStore is instantiated during production ask
    def forbidden_store(*args, **kwargs):
        raise AssertionError("GraphRAGStore should not be instantiated during production QuestionService retrieval.")

    monkeypatch.setattr("GraphRAG.retriever.generate_text", lambda prompt, system_prompt, model, max_tokens: "A cell is the basic unit of life.")
    monkeypatch.setattr("GraphRAG.retriever.embed_question", lambda q: [1.0, 0.0])

    result = asyncio.run(service.ask_async("What is a cell?", collection_id="cell_biology"))

    assert result["answer"] == "A cell is the basic unit of life."
    assert len(fake_adapter.calls) == 1
    assert fake_adapter.calls[0]["query"] == "What is a cell?"
    assert fake_adapter.calls[0]["collection_id"] == "cell_biology"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["documentName"] == "cell.txt"
    assert result["evidence"][0]["text"] == "A cell is the basic structural and functional unit of life."
