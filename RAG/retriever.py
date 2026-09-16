from __future__ import annotations

from typing import Any, Dict, List

from .db import search_documents
from .embeddings import embed_text


def query_rag(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    embedding = embed_text(question)
    return search_documents(embedding, top_k=top_k)
