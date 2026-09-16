from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import fitz

from .db import insert_documents
from .embeddings import embed_batch


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(cleaned):
            break
    return chunks


def extract_text_from_file(path: str | Path) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        doc = fitz.open(file_path)
        pages = [page.get_text("text") for page in doc]
        doc.close()
        return "\n\n".join(pages)

    raise ValueError(f"Unsupported file type: {suffix}")


def ingest_text(text: str, source: str = "manual", metadata: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    chunks = chunk_text(text)
    if not chunks:
        return []

    embeddings = embed_batch(chunks)
    rows = [
        {
            "content": chunk,
            "metadata": {**(metadata or {}), "source": source},
            "embedding": embedding,
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]
    insert_documents(rows)
    return rows


def ingest_file(path: str | Path, source: str | None = None) -> List[Dict[str, Any]]:
    file_path = Path(path)
    content = extract_text_from_file(file_path)
    return ingest_text(content, source=source or str(file_path), metadata={"file_name": file_path.name})


def ingest_texts(texts: Sequence[str], source: str = "manual") -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    for text in texts:
        all_rows.extend(ingest_text(text, source=source))
    return all_rows
