from __future__ import annotations

from typing import Any

from GraphRAG.db import GraphRAGStore


class GraphService:
    """Service wrapper around the shared GraphRAG graph store."""

    def __init__(self, store: GraphRAGStore | None = None):
        self._store = store

    @property
    def store(self) -> GraphRAGStore:
        if self._store is None:
            self._store = GraphRAGStore()
        return self._store

    def list_collections(self) -> list[dict[str, Any]]:
        return self.store.list_collections()

    def create_collection(
        self,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        return self.store.ensure_collection(collection_id, name=name, description=description)

    def get_summary(self) -> list[dict[str, Any]]:
        return self.store.get_graph_summary()

    def get_graph_data(
        self,
        document_name: str | None = None,
        collection_id: str | None = None,
        community_id: int | None = None,
    ) -> dict[str, Any]:
        return self.store.get_graph_data(
            document_name=document_name,
            collection_id=collection_id,
            community_id=community_id,
        )


service = GraphService()
