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


def test_question_service_uses_native_store_for_collection_queries(monkeypatch):
    class DummyStore:
        def close(self):
            pass

    captured = {}

    async def fake_answer_question_async(question, *, collection_id=None, store=None):
        captured["question"] = question
        captured["collection_id"] = collection_id
        captured["store"] = store
        return {"answer": "ok", "path": {"nodes": [], "edges": []}, "evidence": []}

    monkeypatch.setattr("app.services.question_service.GraphRAGStore", lambda: DummyStore())
    monkeypatch.setattr("app.services.question_service.answer_question_async", fake_answer_question_async)

    result = asyncio.run(__import__("app.services.question_service", fromlist=["service"]).service.ask_async("What is a cell?", collection_id="cell_biology"))

    assert result["answer"] == "ok"
    assert captured["collection_id"] == "cell_biology"
    assert isinstance(captured["store"], DummyStore)
