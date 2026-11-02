from __future__ import annotations

import json
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .graphiti_integration import GraphitiAdapter
from .graph_builder import build_graph_data
from .llm import generate_text


class GraphRAGRetriever:
    def __init__(self, store: GraphRAGStore | None = None):
        self.store = store
        self.adapter = GraphitiAdapter()
        self.config = config

    def ask(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")

        question = question.strip()
        evidence = self.adapter.search(question, collection_id=collection_id, limit=self.config.vector_retrieval_count)
        flat_graph = {
            "nodes": [{"id": item["source"], "label": item["source"], "type": "Entity"} for item in evidence]
            + [{"id": item["target"], "label": item["target"], "type": "Entity"} for item in evidence],
            "edges": [{
                "source": item["source"],
                "target": item["target"],
                "label": item["relation"],
                "evidence_records": [{"evidence": item["evidence"]}],
            } for item in evidence],
        }

        if not evidence:
            return {
                "answer": "I could not find enough verified evidence in the Graphiti knowledge graph to answer that question.",
                "path": {"nodes": [], "edges": []},
                "evidence": [],
            }

        context = {
            "question": question,
            "evidence": evidence,
            "graph": flat_graph,
        }

        answer_text = generate_text(
            f"Answer using only the supplied evidence. If there is insufficient information, say so clearly.\n\n{json.dumps(context, ensure_ascii=False)}",
            system_prompt="You answer questions strictly from retrieved graph evidence. Never invent facts or use external knowledge.",
            model=self.config.ollama_chat_model,
            max_tokens=384,
        )

        return {
            "answer": answer_text,
            "path": {"nodes": flat_graph["nodes"], "edges": flat_graph["edges"]},
            "evidence": evidence,
        }


def answer_question(
    question: str,
    *,
    collection_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    return GraphRAGRetriever(store=store).ask(question, collection_id=collection_id)
