from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .db import GraphRAGStore
from .document_loader import extract_document_text
from .graphiti_integration import GraphitiAdapter
from .utils.text_utils import clean_text

logger = logging.getLogger(__name__)

_graphiti_adapter = GraphitiAdapter()


def _safe_document_id(document_name: str, text: str | None = None, collection_id: str = "default") -> str:
    return _graphiti_adapter._document_hash_key(document_name, text, collection_id)


def ingest_document_text(
    document_name: str,
    text: str,
    *,
    collection_id: str | None = None,
    collection_name: str | None = None,
    document_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """Route ingestion through Graphiti while preserving the app’s existing document APIs."""
    return _graphiti_adapter.ingest_document_text(
        document_name,
        text,
        collection_id=collection_id,
        collection_name=collection_name,
        document_id=document_id,
        store=store,
    )


def ingest_file(
    file_path: str,
    *,
    document_name: str | None = None,
    collection_id: str | None = None,
    collection_name: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """Ingest a file from disk into a collection."""
    if not file_path:
        raise ValueError("A file path is required.")
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif extension in {".pdf", ".docx"}:
        text = extract_document_text(str(path), extension)
    else:
        raise ValueError(f"Unsupported document type: {extension}")

    if not text or not text.strip():
        raise ValueError("No readable text was found in the uploaded document.")

    return ingest_document_text(
        document_name or path.name,
        text,
        collection_id=collection_id,
        collection_name=collection_name,
        store=store,
    )
