from __future__ import annotations

from GraphRAG.ingest import ingest_file
from GraphRAG.llm import check_model_available

from app.config import OLLAMA_EMBEDDING_MODEL, OLLAMA_MODEL


class DocumentService:
    """Thin service wrapper around the shared GraphRAG ingestion pipeline."""

    def check_ollama(self) -> None:
        """Validate the required Ollama models before ingesting a document."""
        check_model_available(OLLAMA_MODEL)
        check_model_available(OLLAMA_EMBEDDING_MODEL)

    def ingest(self, file_path: str, *, document_name: str | None = None) -> dict:
        return ingest_file(file_path, document_name=document_name)


service = DocumentService()
