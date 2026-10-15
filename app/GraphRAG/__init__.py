"""Standalone GraphRAG pipeline package for the document graph application."""

from app.config import AppConfig

GraphRAGConfig = AppConfig


def get_config() -> AppConfig:
    return AppConfig().validate()


__all__ = [
    "AppConfig",
    "GraphRAGConfig",
    "get_config",
]
