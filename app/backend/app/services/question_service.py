from __future__ import annotations

import asyncio
from typing import Any

from GraphRAG.db import GraphRAGStore
from GraphRAG.retriever import answer_question, answer_question_async


class QuestionService:
    """Thin service wrapper around the shared GraphRAG answer pipeline."""

    async def ask_async(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")

        store = GraphRAGStore()
        try:
            return await answer_question_async(question.strip(), collection_id=collection_id, store=store)
        finally:
            if hasattr(store, "close"):
                store.close()

    def ask(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ask_async(question.strip(), collection_id=collection_id))
        return self.ask_async(question.strip(), collection_id=collection_id)


service = QuestionService()
