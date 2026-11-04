from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .document_loader import extract_document_text
from .graphiti_integration import GraphitiAdapter
from .utils.text_utils import clean_text, chunk_text

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
    """Respect an injected store; otherwise use the Graphiti-backed default path."""
    if store is not None:
        collection_id = collection_id or "default"
        cleaned = clean_text(text or "")
        if not cleaned:
            raise ValueError("Document text is empty after cleaning.")
        content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        store.ensure_collection(collection_id, name=collection_name or collection_id)
        existing = store.find_document_by_content_hash(content_hash, collection_id=collection_id)
        if existing:
            graph = getattr(store, "get_graph_data", lambda **kwargs: {"nodes": [], "edges": []})(collection_id=collection_id)
            return {
                "document_name": document_name,
                "document_id": existing.get("document_id") or existing.get("id"),
                "collection_id": collection_id,
                "reused": True,
                "message": f"Reused existing graph for '{document_name}' in collection '{collection_id}'.",
                "passages": 0,
                "entities": len(graph.get("nodes", [])),
                "relationships": len(graph.get("edges", [])),
                "graph": graph,
            }

        chunks = chunk_text(cleaned, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
        doc_id = document_id or _safe_document_id(document_name, cleaned, collection_id)
        passage_rows = []
        for index, chunk in enumerate(chunks):
            passage_id = hashlib.sha256(f"{collection_id}|{document_name}|{index}|{chunk}".encode("utf-8")).hexdigest()[:24]
            passage_rows.append({
                "passage_id": passage_id,
                "document_id": doc_id,
                "document_name": document_name,
                "collection_id": collection_id,
                "chunk_index": index,
                "page": None,
                "start_offset": index * max(1, config.chunk_size - config.chunk_overlap),
                "end_offset": (index + 1) * max(1, config.chunk_size - config.chunk_overlap),
                "text": chunk,
                "content_hash": content_hash,
            })
        store.store_document_passages(
            document_name,
            passage_rows,
            document_id=doc_id,
            collection_id=collection_id,
            content_hash=content_hash,
        )
        graph = getattr(store, "get_graph_data", lambda **kwargs: {"nodes": [], "edges": []})(collection_id=collection_id)
        return {
            "document_name": document_name,
            "document_id": doc_id,
            "collection_id": collection_id,
            "reused": False,
            "passages": len(passage_rows),
            "entities": len(graph.get("nodes", [])),
            "relationships": len(graph.get("edges", [])),
            "graph": graph,
        }

    return _graphiti_adapter.ingest_document_text(
        document_name,
        text,
        collection_id=collection_id,
        collection_name=collection_name,
        document_id=document_id,
        store=store,
    )


async def ingest_document_text_async(
    document_name: str,
    text: str,
    *,
    collection_id: str | None = None,
    collection_name: str | None = None,
    document_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """Async ingestion path, respecting an injected store when present."""
    if store is not None:
        return ingest_document_text(
            document_name,
            text,
            collection_id=collection_id,
            collection_name=collection_name,
            document_id=document_id,
            store=store,
        )
    return await _graphiti_adapter.ingest_document_text_async(
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


async def ingest_file_async(
    file_path: str,
    *,
    document_name: str | None = None,
    collection_id: str | None = None,
    collection_name: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """Async file ingestion wrapper."""
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

    return await ingest_document_text_async(
        document_name or path.name,
        text,
        collection_id=collection_id,
        collection_name=collection_name,
        store=store,
    )
