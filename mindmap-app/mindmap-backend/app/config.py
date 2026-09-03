from pydantic import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/mindmap"
    NEO4J_URL: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    PGVECTOR_URL: str = "postgresql://postgres:password@localhost:5432/vector"

    class Config:
        env_file = ".env"


settings = Settings()
from pydantic import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/mindmap"
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    OPENAI_API_KEY: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
