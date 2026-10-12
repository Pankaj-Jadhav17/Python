import math
from collections.abc import Sequence

from .config import config
from .llm import generate_embedding, generate_embeddings


def validate_embedding_vector(vector: Sequence[float], *, expected_dim: int | None = None) -> list[float]:
    if vector is None:
        raise ValueError("Embedding vector is required.")
    if not isinstance(vector, (list, tuple)):
        raise ValueError("Embedding vector must be a list or tuple of floats.")
    if len(vector) == 0:
        raise ValueError("Embedding vector cannot be empty.")
    values = [float(value) for value in vector]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Embedding vector contains NaN or infinity.")
    if expected_dim is not None and len(values) != expected_dim:
        raise ValueError(f"Embedding dimension mismatch: expected {expected_dim}, got {len(values)}.")
    return values


def embed_texts(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    if not texts:
        return []
    cleaned = [str(text).strip() for text in texts if str(text).strip()]
    if not cleaned:
        raise ValueError("No non-empty text values were provided for embedding.")
    vectors = generate_embeddings(cleaned, model=model)
    if not vectors:
        raise ValueError("Embedding generation produced no vectors.")
    expected_dim = None
    for vector in vectors:
        validated = validate_embedding_vector(vector)
        if expected_dim is None:
            expected_dim = len(validated)
        elif len(validated) != expected_dim:
            raise ValueError("Embedding dimensions are inconsistent within the batch.")
    return [validate_embedding_vector(vector, expected_dim=expected_dim) for vector in vectors]


def embed_question(question: str, *, model: str | None = None) -> list[float]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty.")
    vector = generate_embedding(question.strip(), model=model or config.ollama_embedding_model)
    return validate_embedding_vector(vector, expected_dim=len(vector))


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    left = validate_embedding_vector(first)
    right = validate_embedding_vector(second)
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have the same length for cosine similarity.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
