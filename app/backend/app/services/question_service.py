from __future__ import annotations

import asyncio
from typing import Any

from GraphRAG.graphiti_integration import GraphitiAdapter, get_shared_graphiti_adapter
from GraphRAG.retriever import GraphRAGRetriever, answer_question_async


class QuestionService:
    """Service wrapper around the Graphiti-backed retrieval and answer pipeline."""

    def __init__(
        self,
        adapter: GraphitiAdapter | None = None,
        retriever: GraphRAGRetriever | None = None,
    ):
        self._adapter = adapter
        self._retriever = retriever

    @property
    def retriever(self) -> GraphRAGRetriever:
        if self._retriever is None:
            adapter = self._adapter if self._adapter is not None else get_shared_graphiti_adapter()
            self._retriever = GraphRAGRetriever(adapter=adapter)
        return self._retriever

    async def ask_async(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")

        return await self.retriever.ask_async(question.strip(), collection_id=collection_id)

    def ask(self, question: str, collection_id: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must not be empty.")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ask_async(question.strip(), collection_id=collection_id))
        return self.ask_async(question.strip(), collection_id=collection_id)


service = QuestionService()
