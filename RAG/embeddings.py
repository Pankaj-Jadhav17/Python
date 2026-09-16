from __future__ import annotations

from typing import Iterable, List, Sequence

from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> List[float]:
    model = get_model()
    vector = model.encode(text, convert_to_numpy=True)
    return vector.astype(float).tolist()


def embed_batch(texts: Sequence[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(list(texts), convert_to_numpy=True)
    return vectors.astype(float).tolist()


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    return embed_batch(list(texts))
