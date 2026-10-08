from fastapi.testclient import TestClient

from app.main import app
from app.routers import ask
from app.services.graph_question_service import PLAN_SCHEMA, GraphQuestionService


def test_question_workflow_returns_answer_path_and_verified_evidence():
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, query: str, **parameters):
            calls.append((query, parameters))
            if "RETURN c.canonical_name AS name" in query:
                return [
                    {"name": "microspore", "aliases": []},
                    {"name": "pollen grain", "aliases": ["pollen"]},
                ]
            if "RETURN DISTINCT source.canonical_name" in query:
                return [
                    {
                        "source": "microspore",
                        "target": "pollen grain",
                        "relation": "develops into",
                        "evidence": "The microspore develops into a pollen grain.",
                        "page": 14,
                        "passageId": "passage-14",
                        "confidence": 0.94,
                        "documentName": "biology.pdf",
                        "status": "verified",
                    }
                ]
            raise AssertionError(f"Unexpected Cypher query: {query}")

    class Driver:
        def session(self):
            return Session()

    service = GraphQuestionService(Driver())
    service._call_chat = lambda _system, _prompt, schema: (
        {"action": "neighbors", "concepts": ["microspore"]}
        if schema is PLAN_SCHEMA
        else {"answer": "A microspore develops into a pollen grain."}
    )
    service._embed_texts = lambda texts: [
        [1.0, 0.0] if "microspore" in text.casefold() else [0.0, 1.0]
        for text in texts
    ]

    result = service.ask("What develops from a microspore?")

    assert result["answer"] == "A microspore develops into a pollen grain."
    assert result["path"]["nodes"] == [
        {"id": "concept:microspore", "label": "microspore", "type": "Concept"},
        {"id": "concept:pollen grain", "label": "pollen grain", "type": "Concept"},
    ]
    assert result["path"]["edges"][0]["label"] == "develops into"
    assert result["evidence"][0]["quote"] == "The microspore develops into a pollen grain."
    assert set(result) == {"answer", "path", "evidence"}
    assert calls[-1][1]["concept_names"] == ["microspore"]
    assert "r.status = 'verified'" in calls[-1][0]


def test_path_action_requires_at_least_two_concepts():
    assert GraphQuestionService._select_tool({"action": "path", "concepts": ["ovule"]}) == "neighbors"
    assert GraphQuestionService._select_tool({"action": "path", "concepts": ["ovule", "seed"]}) == "path"


def test_concept_matching_uses_exact_plural_forms_before_embeddings():
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, *_args, **_kwargs):
            return [
                {"name": "microspore", "aliases": []},
                {"name": "pollen grain", "aliases": []},
            ]

    class Driver:
        def session(self):
            return Session()

    service = GraphQuestionService(Driver())
    service._embed_texts = lambda _texts: (_ for _ in ()).throw(
        AssertionError("Exact graph names should not need embedding calls.")
    )

    assert service._match_concepts(["microspores", "pollen grains"]) == [
        "microspore",
        "pollen grain",
    ]


def test_path_tool_returns_ordered_path_and_evidence():
    cypher = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, query: str, **parameters):
            cypher.append((query, parameters))
            if "RETURN c.canonical_name AS name" in query:
                return [{"name": "alpha", "aliases": []}, {"name": "beta", "aliases": []}]
            if "shortestPath" in query:
                return [
                    {
                        "node_names": ["alpha", "beta"],
                        "edges": [
                            {
                                "source": "alpha",
                                "target": "beta",
                                "relation": "connects to",
                                "evidence": "Alpha connects to beta.",
                                "page": 2,
                                "passageId": "passage-2",
                                "confidence": 0.91,
                                "documentName": "source.pdf",
                                "status": "verified",
                            }
                        ],
                    }
                ]
            raise AssertionError(f"Unexpected Cypher query: {query}")

    class Driver:
        def session(self):
            return Session()

    service = GraphQuestionService(Driver())
    service._call_chat = lambda _system, _prompt, schema: (
        {"action": "path", "concepts": ["alpha", "beta"]}
        if schema is PLAN_SCHEMA
        else {"answer": "Alpha connects to beta."}
    )
    service._embed_texts = lambda texts: [
        [1.0, 0.0] if text.casefold() == "alpha" else [0.0, 1.0]
        for text in texts
    ]

    result = service.ask("How is alpha connected to beta?")

    assert result["path"]["nodes"] == [
        {"id": "concept:alpha", "label": "alpha", "type": "Concept"},
        {"id": "concept:beta", "label": "beta", "type": "Concept"},
    ]
    assert result["path"]["edges"][0]["source"] == "concept:alpha"
    assert result["path"]["edges"][0]["target"] == "concept:beta"
    assert result["evidence"][0]["documentName"] == "source.pdf"
    path_query, path_parameters = cypher[-1]
    assert "shortestPath" in path_query
    assert "r.status = 'verified'" in path_query
    assert path_parameters["concept_names"] == ["alpha", "beta"]


def test_ask_endpoint_returns_answer_path_and_evidence(monkeypatch):
    expected = {
        "answer": "A microspore develops into a pollen grain.",
        "path": {"nodes": [], "edges": []},
        "evidence": [],
    }

    class StubQuestionService:
        def ask(self, question: str) -> dict:
            assert question == "What develops from a microspore?"
            return expected

    monkeypatch.setattr(ask, "question_service", StubQuestionService())

    response = TestClient(app).post(
        "/ask",
        json={"question": "What develops from a microspore?"},
    )

    assert response.status_code == 200
    assert response.json() == expected
