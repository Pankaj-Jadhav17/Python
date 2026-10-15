import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be numeric.") from exc


@dataclass(frozen=True)
class AppConfig:
    postgres_url: str | None = os.getenv("POSTGRES_URL")
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "neo4j")
    ollama_base_url: str = (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") or "http://localhost:11434").rstrip("/")
    ollama_chat_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma:latest")
    request_timeout_seconds: int = _env_int("OLLAMA_TIMEOUT_SECONDS", 180)
    chunk_size: int = _env_int("GRAPHRAG_CHUNK_SIZE", 1800)
    chunk_overlap: int = _env_int("GRAPHRAG_CHUNK_OVERLAP", 180)
    vector_retrieval_count: int = _env_int("GRAPHRAG_VECTOR_RETRIEVAL_COUNT", 8)
    graph_traversal_depth: int = _env_int("GRAPHRAG_GRAPH_TRAVERSAL_DEPTH", 2)
    max_graph_nodes: int = _env_int("GRAPHRAG_MAX_GRAPH_NODES", 80)
    max_graph_edges: int = _env_int("GRAPHRAG_MAX_GRAPH_EDGES", 120)
    ollama_confidence_threshold: float = _env_float("OLLAMA_CONFIDENCE_THRESHOLD", 0.72)
    ollama_num_predict: int = _env_int("OLLAMA_NUM_PREDICT", 384)
    ask_concept_similarity_threshold: float = _env_float("ASK_CONCEPT_SIMILARITY_THRESHOLD", 0.35)
    ask_max_concepts: int = _env_int("ASK_MAX_CONCEPTS", 2000)

    def validate(self) -> "AppConfig":
        if not self.neo4j_uri:
            raise ValueError("NEO4J_URI is required.")
        if not self.neo4j_user:
            raise ValueError("NEO4J_USER is required.")
        if not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required.")
        if not self.ollama_base_url:
            raise ValueError("OLLAMA_BASE_URL is required.")
        if not self.ollama_chat_model:
            raise ValueError("OLLAMA_MODEL is required.")
        if not self.ollama_embedding_model:
            raise ValueError("OLLAMA_EMBEDDING_MODEL is required.")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be > 0.")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0.")
        if self.vector_retrieval_count <= 0:
            raise ValueError("vector_retrieval_count must be > 0.")
        if self.graph_traversal_depth <= 0:
            raise ValueError("graph_traversal_depth must be > 0.")
        if self.max_graph_nodes <= 0:
            raise ValueError("max_graph_nodes must be > 0.")
        if self.max_graph_edges <= 0:
            raise ValueError("max_graph_edges must be > 0.")
        return self


POSTGRES_URL = os.getenv("POSTGRES_URL")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") or "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma:latest")
OLLAMA_TIMEOUT_SECONDS = _env_int("OLLAMA_TIMEOUT_SECONDS", 180)
OLLAMA_CONFIDENCE_THRESHOLD = _env_float("OLLAMA_CONFIDENCE_THRESHOLD", 0.72)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 384)
ASK_CONCEPT_SIMILARITY_THRESHOLD = _env_float("ASK_CONCEPT_SIMILARITY_THRESHOLD", 0.35)
ASK_MAX_CONCEPTS = _env_int("ASK_MAX_CONCEPTS", 2000)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

config = AppConfig().validate()