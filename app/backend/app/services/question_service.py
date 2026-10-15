from __future__ import annotations

from GraphRAG.retriever import answer_question


class QuestionService:
    """Thin service wrapper around the shared GraphRAG answer pipeline."""

    def ask(self, question: str) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        return answer_question(question.strip())


service = QuestionService()
