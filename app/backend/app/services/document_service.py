from __future__ import annotations

import asyncio
from typing import Any

from GraphRAG.ingest import ingest_file, ingest_file_async
from GraphRAG.llm import check_model_available

from app.config import OLLAMA_EMBEDDING_MODEL, OLLAMA_MODEL


class DocumentService:
    """Service wrapper around the shared GraphRAG ingestion pipeline."""

    def check_ollama(self) -> None:
        """Validate the required Ollama models before ingesting a document."""
        check_model_available(OLLAMA_MODEL)
        check_model_available(OLLAMA_EMBEDDING_MODEL)

    async def ingest_async(
        self,
        file_path: str,
        *,
        document_name: str | None = None,
        collection_id: str | None = None,
        collection_name: str | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> dict[str, Any]:
        return await ingest_file_async(
            file_path,
            document_name=document_name,
            collection_id=collection_id,
            collection_name=collection_name,
            start_page=start_page,
            end_page=end_page,
        )

    def ingest(
        self,
        file_path: str,
        *,
        document_name: str | None = None,
        collection_id: str | None = None,
        collection_name: str | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.ingest_async(
                    file_path,
                    document_name=document_name,
                    collection_id=collection_id,
                    collection_name=collection_name,
                    start_page=start_page,
                    end_page=end_page,
                )
            )
        return self.ingest_async(
            file_path,
            document_name=document_name,
            collection_id=collection_id,
            collection_name=collection_name,
            start_page=start_page,
            end_page=end_page,
        )


service = DocumentService()
