from __future__ import annotations

from GraphRAG.db import GraphRAGStore


class GraphService:
    """Thin service wrapper around the shared GraphRAG graph store."""

    def __init__(self, store: GraphRAGStore | None = None):
        self._store = store

    @property
    def store(self) -> GraphRAGStore:
        if self._store is None:
            self._store = GraphRAGStore()
        return self._store

    def get_summary(self) -> list[dict]:
        return self.store.get_graph_summary()

    def get_graph_data(self, document_name: str | None = None) -> dict:
        return self.store.get_graph_data(document_name)


service = GraphService()
