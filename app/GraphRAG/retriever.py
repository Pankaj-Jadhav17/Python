from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .embeddings import embed_question
from .graphiti_integration import GraphitiAdapter
from .llm import generate_text


class GraphRAGRetriever:
    def __init__(self, store: GraphRAGStore | None = None):
        self.store = store
        self.adapter = None if store is not None else GraphitiAdapter()
        self.config = config

    def _coerce_evidence(self, raw_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for item in raw_evidence or []:
            if not isinstance(item, dict):
                continue
            evidence.append({
                "source": item.get("source") or item.get("subject") or item.get("name") or "",
                "target": item.get("target") or item.get("object") or item.get("entity") or "",
                "relation": item.get("relation") or item.get("label") or "related_to",
                "evidence": item.get("evidence") or item.get("text") or item.get("summary") or "",
                "documentName": item.get("documentName") or item.get("document_name") or "",
                "passageId": item.get("passageId") or item.get("passage_id") or "",
                "page": item.get("page"),
                "confidence": item.get("confidence", 0.0),
                "collection_id": item.get("collection_id") or item.get("group_id"),
            })
        return evidence

    def _build_path(self, question: str, evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        edges: list[dict[str, Any]] = []
        for item in evidence:
            source = item.get("source") or item.get("documentName") or "question"
            target = item.get("target") or item.get("documentName") or question
            if source and target:
                edges.append({
                    "source": source,
                    "target": target,
                    "label": item.get("relation") or "supports",
                    "evidence_records": [{"evidence": item.get("evidence") or ""}],
                })

        if not edges and evidence:
            first = evidence[0]
            fallback_source = first.get("documentName") or "question"
            fallback_target = first.get("source") or first.get("target") or question
            edges.append({
                "source": fallback_source,
                "target": fallback_target,
                "label": "supports",
                "evidence_records": [{"evidence": first.get("evidence") or ""}],
            })

        nodes = [
            {"id": edge["source"], "label": edge["source"], "type": "Entity"}
            for edge in edges
        ] + [
            {"id": edge["target"], "label": edge["target"], "type": "Entity"}
            for edge in edges
        ]
        unique_nodes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in nodes:
            node_id = node["id"]
            if node_id in seen:
                continue
            seen.add(node_id)
            unique_nodes.append(node)
        return {"nodes": unique_nodes, "edges": edges}

    async def ask_async(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")

        question = question.strip()
        if self.store is not None and hasattr(self.store, "search_similar_passages"):
            question_vector = embed_question(question)
            method = self.store.search_similar_passages
            params = inspect.signature(method).parameters
            if "collection_id" in params or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
                evidence_rows = method(
                    question_vector,
                    limit=self.config.vector_retrieval_count,
                    collection_id=collection_id,
                )
            else:
                evidence_rows = method(question_vector, limit=self.config.vector_retrieval_count)
            evidence = self._coerce_evidence(evidence_rows)
            if hasattr(self.store, "expand_graph"):
                graph_method = self.store.expand_graph
                graph_params = inspect.signature(graph_method).parameters
                if "collection_id" in graph_params or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in graph_params.values()):
                    expanded = graph_method(
                        evidence,
                        depth=self.config.graph_traversal_depth,
                        collection_id=collection_id,
                    )
                else:
                    expanded = graph_method(evidence, depth=self.config.graph_traversal_depth)
                if expanded:
                    evidence.extend(self._coerce_evidence(expanded))
        else:
            if self.adapter is None:
                raise RuntimeError("A store-backed retriever cannot fall back to Graphiti without a default adapter.")
            evidence = self._coerce_evidence(
                await self.adapter.search_async(question, collection_id=collection_id, limit=self.config.vector_retrieval_count)
            )

        if not evidence:
            return {
                "answer": "I could not find enough verified evidence in the Graphiti knowledge graph to answer that question.",
                "path": {"nodes": [], "edges": []},
                "evidence": [],
            }

        flat_graph = self._build_path(question, evidence)
        context = {"question": question, "evidence": evidence, "graph": flat_graph}
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

    def ask(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ask_async(question.strip(), collection_id=collection_id))
        return self.ask_async(question.strip(), collection_id=collection_id)


def answer_question(
    question: str,
    *,
    collection_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    return GraphRAGRetriever(store=store).ask(question, collection_id=collection_id)


async def answer_question_async(
    question: str,
    *,
    collection_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    return await GraphRAGRetriever(store=store).ask_async(question, collection_id=collection_id)
