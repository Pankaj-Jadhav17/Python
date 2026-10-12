import json

from .config import config
from .db import GraphRAGStore
from .embeddings import cosine_similarity, embed_question
from .graph_builder import build_graph_data
from .llm import generate_text


class GraphRAGRetriever:
    def __init__(self, store: GraphRAGStore | None = None):
        self.store = store or GraphRAGStore()
        self.config = config

    def ask(self, question: str) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        question = question.strip()
        question_vector = embed_question(question)
        passages = self.store.search_similar_passages(question_vector, limit=self.config.vector_retrieval_count)
        evidence: list[dict] = []
        for passage in passages:
            evidence.append({
                "source": passage.get("document_name") or "document",
                "target": passage.get("passage_id") or "passage",
                "relation": "contains relevant passage",
                "evidence": passage.get("text"),
                "page": passage.get("page"),
                "passageId": passage.get("passage_id"),
                "documentName": passage.get("document_name"),
                "confidence": passage.get("score", 0.0),
                "status": "verified",
            })

        expanded = self.store.expand_graph(evidence, depth=self.config.graph_traversal_depth)
        flat_graph = build_graph_data([
            {
                "subject": item.get("source") or item.get("document_name") or "unknown",
                "relation": item.get("relation") or "related to",
                "object": item.get("target") or item.get("passage_id") or "unknown",
                "evidence": item.get("evidence") or "",
                "confidence": item.get("confidence", 0.0),
                "page": item.get("page"),
                "passage_id": item.get("passage_id"),
                "document_name": item.get("document_name"),
                "status": item.get("status", "verified"),
            }
            for item in expanded or evidence
        ], max_nodes=self.config.max_graph_nodes, max_edges=self.config.max_graph_edges)

        if not evidence and not expanded:
            return {
                "answer": "I could not find enough verified evidence in the graph to answer that question.",
                "path": {"nodes": [], "edges": []},
                "evidence": [],
            }

        context = {
            "question": question,
            "evidence": evidence + expanded,
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
            "evidence": evidence + expanded,
        }


def answer_question(question: str, *, store: GraphRAGStore | None = None) -> dict:
    return GraphRAGRetriever(store=store).ask(question)
