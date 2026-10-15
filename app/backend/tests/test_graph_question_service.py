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
