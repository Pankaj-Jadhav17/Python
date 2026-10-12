import math

import pytest

from GraphRAG.config import GraphRAGConfig
from GraphRAG.embeddings import validate_embedding_vector
from GraphRAG.utils.text_utils import clean_text, chunk_text


def test_graph_rag_config_validates_runtime_values():
    config = GraphRAGConfig()
    assert config.ollama_base_url
    assert config.chunk_size > 0
    assert config.chunk_overlap >= 0
    assert config.vector_retrieval_count > 0
    assert config.graph_traversal_depth > 0
    assert config.max_graph_nodes > 0
    assert config.max_graph_edges > 0


def test_text_cleaning_and_chunking_preserve_content():
    cleaned = clean_text("  This is\n a test.   ")
    assert "This is a test." in cleaned
    chunks = chunk_text(cleaned, chunk_size=15, overlap=5)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


def test_embedding_validation_rejects_bad_vectors():
    validate_embedding_vector([0.1, 0.2, 0.3])
    with pytest.raises(ValueError):
        validate_embedding_vector([])
    with pytest.raises(ValueError):
        validate_embedding_vector([0.1, float("nan"), 0.3])
    with pytest.raises(ValueError):
        validate_embedding_vector([0.1, math.inf, 0.3])
