from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .embeddings import embed_question
from .graphiti_integration import GraphitiAdapter, get_shared_graphiti_adapter
from .llm import generate_text

logger = logging.getLogger(__name__)


class GraphRAGRetriever:
    def __init__(self, store: GraphRAGStore | None = None, adapter: GraphitiAdapter | None = None):
        self.store = store
        self.adapter = adapter if adapter is not None else (None if store is not None else get_shared_graphiti_adapter())
        self.config = config

    def _coerce_evidence(self, raw_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for item in raw_evidence or []:
            if not isinstance(item, dict):
                continue
            doc_name = item.get("documentName") or item.get("document_name") or ""
            p_id = item.get("passageId") or item.get("passage_id") or item.get("episode_id") or ""
            text_val = item.get("evidence") or item.get("text") or item.get("summary") or ""
            evidence.append({
                "source": item.get("source") or item.get("subject") or item.get("name") or "",
                "target": item.get("target") or item.get("object") or item.get("entity") or "",
                "relation": item.get("relation") or item.get("label") or "related_to",
                "evidence": text_val,
                "text": text_val,
                "documentName": doc_name,
                "document_name": doc_name,
                "passageId": p_id,
                "passage_id": p_id,
                "episode_id": item.get("episode_id") or p_id,
                "document_id": item.get("document_id") or "",
                "page": item.get("page"),
                "chunk_index": item.get("chunk_index"),
                "confidence": item.get("confidence", 0.0),
                "score": item.get("score"),
                "collection_id": item.get("collection_id") or item.get("group_id"),
            })
        return evidence

    def _build_path(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        nodes: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        graph_edges: list[dict[str, Any]] = []

        if edges:
            for item in edges:
                src = item.get("source")
                tgt = item.get("target")
                if src and tgt:
                    ev_records = item.get("evidence_records", [])
                    if not ev_records and (item.get("evidence") or item.get("text")):
                        ev_records = [{
                            "evidence": item.get("evidence") or item.get("text"),
                            "text": item.get("evidence") or item.get("text"),
                            "document_name": item.get("documentName") or item.get("document_name") or "",
                            "page": item.get("page"),
                        }]
                    graph_edges.append({
                        "source": src,
                        "target": tgt,
                        "label": item.get("relation") or item.get("label") or "related_to",
                        "evidence": item.get("evidence") or item.get("text") or "",
                        "evidence_records": ev_records,
                        "document_names": item.get("document_names") or ([item.get("documentName")] if item.get("documentName") else []),
                        "passage_ids": item.get("passage_ids", []),
                    })

        # Only create synthetic graph edges when edges argument is None (legacy store mode).
        # When edges is provided explicitly (e.g. empty list [] from Graphiti), return empty edges!
        if edges is None and not graph_edges and evidence:
            for item in evidence:
                source = item.get("source") or item.get("documentName") or item.get("document_name") or "question"
                target = item.get("target") or item.get("documentName") or item.get("document_name") or question
                if source and target:
                    graph_edges.append({
                        "source": source,
                        "target": target,
                        "label": item.get("relation") or "supports",
                        "evidence": item.get("evidence") or item.get("text") or "",
                        "evidence_records": [{"evidence": item.get("evidence") or item.get("text") or ""}],
                        "document_names": [item.get("documentName") or item.get("document_name")] if (item.get("documentName") or item.get("document_name")) else [],
                        "passage_ids": [item.get("passageId") or item.get("passage_id")] if (item.get("passageId") or item.get("passage_id")) else [],
                    })

        if edges is None and not graph_edges and evidence:
            first = evidence[0]
            fallback_source = first.get("documentName") or first.get("document_name") or "question"
            fallback_target = first.get("source") or first.get("target") or question
            graph_edges.append({
                "source": fallback_source,
                "target": fallback_target,
                "label": "supports",
                "evidence": first.get("evidence") or first.get("text") or "",
                "evidence_records": [{"evidence": first.get("evidence") or first.get("text") or ""}],
            })

        unique_nodes: list[dict[str, Any]] = []
        seen: set[str] = set()

        for edge in graph_edges:
            for end in ("source", "target"):
                node_id = edge[end]
                if node_id and node_id not in seen:
                    seen.add(node_id)
                    unique_nodes.append({
                        "id": node_id,
                        "label": node_id,
                        "type": "Entity",
                    })

        # Only include disconnected nodes if graph_edges exist or caller provided nodes
        if nodes and graph_edges:
            for n in nodes:
                n_id = n.get("name") or n.get("id") or n.get("uuid")
                if n_id and str(n_id) not in seen:
                    seen.add(str(n_id))
                    unique_nodes.append({
                        "id": str(n_id),
                        "label": n.get("label") or n.get("name") or str(n_id),
                        "type": n.get("type", "Entity"),
                    })

        return {"nodes": unique_nodes, "edges": graph_edges}

    async def ask_async(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")

        question = question.strip()
        logger.info("ask_async initiated: question='%s', collection_id='%s'", question, collection_id)

        edges: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        episodes: list[dict[str, Any]] = []
        communities: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []

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
            flat_graph = self._build_path(question, evidence, edges=None, nodes=None)
        else:
            if self.adapter is None:
                self.adapter = get_shared_graphiti_adapter()

            search_result = await self.adapter.search_async(
                question,
                collection_id=collection_id,
                limit=self.config.vector_retrieval_count,
            )

            if isinstance(search_result, dict):
                edges = search_result.get("edges", []) or []
                nodes = search_result.get("nodes", []) or []
                episodes = search_result.get("episodes", []) or []
                communities = search_result.get("communities", []) or []
                passages = search_result.get("passages", []) or []
                if passages:
                    evidence = self._coerce_evidence(passages)
                else:
                    evidence = []

                # Critical fix: Ensure retrieved episodes reach evidence if not already present
                if episodes:
                    seen_pids = {
                        e.get("passage_id") or e.get("episode_id")
                        for e in evidence
                        if (e.get("passage_id") or e.get("episode_id"))
                    }
                    for idx, ep in enumerate(episodes):
                        if not isinstance(ep, dict):
                            continue
                        p_id = ep.get("uuid") or ep.get("id") or ep.get("passage_id") or ""
                        p_text = ep.get("content") or ep.get("text") or ep.get("body") or ep.get("evidence") or ""
                        if p_text and (not p_id or p_id not in seen_pids):
                            doc_name = ep.get("document_name") or ep.get("documentName") or ""
                            if not doc_name and ep.get("source_description"):
                                m = re.search(r"Document '([^']+)'", ep["source_description"])
                                if m:
                                    doc_name = m.group(1)
                            ep_item = {
                                "passage_id": p_id,
                                "passageId": p_id,
                                "episode_id": p_id,
                                "document_id": ep.get("document_id") or "",
                                "document_name": doc_name,
                                "documentName": doc_name,
                                "collection_id": ep.get("collection_id") or ep.get("group_id") or collection_id,
                                "text": p_text,
                                "evidence": p_text,
                                "chunk_index": ep.get("chunk_index"),
                                "page": ep.get("page"),
                                "score": ep.get("score"),
                            }
                            evidence.append(self._coerce_evidence([ep_item])[0])
                            if p_id:
                                seen_pids.add(p_id)

                if not evidence and edges:
                    evidence = self._coerce_evidence(edges)
            elif isinstance(search_result, list):
                edges = search_result
                evidence = self._coerce_evidence(edges)

            flat_graph = self._build_path(question, evidence, edges=edges, nodes=nodes)

        # Filter for genuine usable textual evidence
        usable_evidence = [
            e for e in evidence
            if (e.get("text") or e.get("evidence") or "").strip()
        ]
        usable_edge_evidence = [
            e for e in edges
            if (e.get("evidence") or e.get("text") or "").strip()
        ]

        logger.info(
            "Graphiti retrieval summary: collection_id='%s', nodes_count=%d, edges_count=%d, "
            "episodes_count=%d, usable_passages_count=%d, total_evidence_count=%d",
            collection_id,
            len(nodes),
            len(edges),
            len(episodes),
            len(usable_evidence),
            len(evidence),
        )

        # Case B: No usable source evidence exists -> Return verified no-evidence response
        if not usable_evidence and not usable_edge_evidence:
            logger.info("No usable source evidence exists for collection '%s'; returning fallback.", collection_id)
            return {
                "answer": "I could not find enough verified evidence in the Graphiti knowledge graph to answer that question.",
                "path": {"nodes": [], "edges": []},
                "evidence": [],
                "nodes": [],
                "communities": [],
            }

        # Build prompt using retrieved original source text as primary evidence and graph relations as context
        context_parts: list[str] = []
        if usable_evidence:
            context_parts.append("--- RETRIEVED SOURCE PASSAGES ---")
            for idx, item in enumerate(usable_evidence, 1):
                doc_name = item.get("documentName") or item.get("document_name") or "Unknown Document"
                page_str = f", Page {item['page']}" if item.get("page") is not None else ""
                chunk_str = f", Chunk {item['chunk_index'] + 1}" if item.get("chunk_index") is not None else ""
                passage_text = item.get("text") or item.get("evidence") or ""
                context_parts.append(f"[{idx}] Document: {doc_name}{page_str}{chunk_str}\n{passage_text}\n")

        if flat_graph["edges"]:
            context_parts.append("--- GRAPH RELATIONSHIPS ---")
            for edge in flat_graph["edges"]:
                s = edge.get("source", "")
                r = edge.get("label", "related_to")
                t = edge.get("target", "")
                fact = ""
                if edge.get("evidence_records"):
                    fact = edge["evidence_records"][0].get("evidence") or edge["evidence_records"][0].get("text") or ""
                elif edge.get("evidence"):
                    fact = edge.get("evidence", "")
                context_parts.append(f"- {s} --[{r}]--> {t}" + (f": {fact}" if fact else ""))

        if communities:
            context_parts.append("--- TOPIC COMMUNITIES ---")
            for comm in communities[:3]:
                c_name = comm.get("name") or comm.get("id") or ""
                c_sum = comm.get("summary") or ""
                if c_sum:
                    context_parts.append(f"- {c_name}: {c_sum}")

        prompt = (
            f"Question: {question}\n\n"
            f"Context:\n"
            f"{chr(10).join(context_parts)}\n\n"
            "Instructions:\n"
            "Answer the question using the retrieved source passages as primary evidence and graph relationships as supporting context.\n"
            "Combine relevant information across multiple passages when multiple passages support the answer.\n"
            "Cite the source document name for claims made where available.\n"
            "If the provided evidence does not contain sufficient information to answer the question, clearly state that there is insufficient evidence in the knowledge graph.\n"
            "Do not extrapolate, assume, or invent facts outside the retrieved evidence."
        )

        logger.info(
            "Invoking Ollama LLM model '%s' (evidence items: %d)",
            self.config.ollama_chat_model,
            len(usable_evidence),
        )

        # Case C: Record actual generation failure without misrepresenting it as retrieval failure
        try:
            answer_text = generate_text(
                prompt,
                system_prompt=(
                    "You answer questions strictly from retrieved graph evidence and document passages. "
                    "Combine relevant information when multiple passages support the answer. "
                    "Never invent facts or use external knowledge. Always cite source documents."
                ),
                model=self.config.ollama_chat_model,
                max_tokens=384,
            )
        except Exception as exc:
            logger.error("Ollama LLM generation invocation failed for model '%s': %s", self.config.ollama_chat_model, exc)
            raise

        # Case D: Detect and handle empty LLM response
        if not isinstance(answer_text, str) or not answer_text.strip():
            logger.error("Ollama LLM returned an empty response for model '%s'", self.config.ollama_chat_model)
            raise RuntimeError("Ollama returned an empty response.")

        logger.info(
            "Ollama LLM generation successful for model '%s', final answer length: %d chars",
            self.config.ollama_chat_model,
            len(answer_text),
        )

        return {
            "answer": answer_text,
            "path": {"nodes": flat_graph["nodes"], "edges": flat_graph["edges"]},
            "evidence": usable_evidence,
            "nodes": nodes,
            "communities": communities,
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
    adapter: GraphitiAdapter | None = None,
) -> dict[str, Any]:
    return GraphRAGRetriever(store=store, adapter=adapter).ask(question, collection_id=collection_id)


async def answer_question_async(
    question: str,
    *,
    collection_id: str | None = None,
    store: GraphRAGStore | None = None,
    adapter: GraphitiAdapter | None = None,
) -> dict[str, Any]:
    return await GraphRAGRetriever(store=store, adapter=adapter).ask_async(question, collection_id=collection_id)
