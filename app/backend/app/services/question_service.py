from __future__ import annotations

from typing import Any

from GraphRAG.retriever import answer_question


class QuestionService:
    """Thin service wrapper around the shared GraphRAG answer pipeline."""

    def ask(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        return answer_question(question.strip(), collection_id=collection_id)


service = QuestionService()
