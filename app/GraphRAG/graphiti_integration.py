from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .embeddings import embed_texts
from .llm import check_model_available
from .utils.text_utils import clean_text, chunk_text

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None

try:
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder import OpenAIRerankerClient
    from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.graphiti import EpisodeType
    from graphiti_core.llm_client import LLMConfig, OpenAIClient
except ImportError:  # pragma: no cover
    Graphiti = None
    OpenAIRerankerClient = None
    OpenAIEmbedder = None
    OpenAIEmbedderConfig = None
    EpisodeType = None
    LLMConfig = None
    OpenAIClient = None


def normalize_group_id(value: str | None, *, default: str = "default") -> str:
    if not value or not str(value).strip():
        return default
    cleaned = str(value).strip()
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", cleaned)
    normalized = normalized.strip("_")
    normalized = normalized.lower()
    return normalized or default


class GraphitiAdapter:
    """Compatibility layer that keeps the app’s contracts while routing graph work through Graphiti."""

    def __init__(self, graphiti: Any | None = None):
        self._graphiti = graphiti
        self._neo4j_driver = None

    @property
    def graphiti(self) -> Any:
        if self._graphiti is None:
            self._graphiti = self._build_graphiti()
        return self._graphiti

    @property
    def neo4j_driver(self):
        if self._neo4j_driver is None:
            if GraphDatabase is None:
                raise RuntimeError("neo4j package is required for Graphiti metadata and graph views.")
            self._neo4j_driver = GraphDatabase.driver(
                config.neo4j_uri,
                auth=(config.neo4j_user, config.neo4j_password),
            )
        return self._neo4j_driver

    @property
    def supports_live_metadata(self) -> bool:
        return self._graphiti is None or hasattr(self._graphiti, "driver")

    def _build_graphiti(self) -> Any:
        if Graphiti is None:
            raise RuntimeError(
                "graphiti-core is not installed. Add it to the backend environment before using Graphiti-backed graph ingestion."
            )

        base_url = f"{config.ollama_base_url.rstrip('/')}/v1"
        llm_config = LLMConfig(
            api_key="ollama",
            model=config.ollama_chat_model,
            base_url=base_url,
            max_tokens=int(getattr(config, "ollama_num_predict", 384)),
        )
        embedder_config = OpenAIEmbedderConfig(
            api_key="ollama",
            base_url=base_url,
            embedding_model=config.ollama_embedding_model,
        )

        llm_client = OpenAIClient(config=llm_config)
        embedder = OpenAIEmbedder(config=embedder_config)
        reranker = OpenAIRerankerClient(config=llm_config, client=llm_client.client)

        return Graphiti(
            uri=config.neo4j_uri,
            user=config.neo4j_user,
            password=config.neo4j_password,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker,
        )

    def validate_ollama_models(self) -> None:
        check_model_available(config.ollama_chat_model)
        check_model_available(config.ollama_embedding_model)

    def ensure_collection(self, collection_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        collection_id = normalize_group_id(collection_id, default="default")
        if not self.supports_live_metadata:
            return {"id": collection_id, "name": (name or collection_id.replace("_", " ")).strip() or collection_id}
        try:
            with self.neo4j_driver.session() as session:
                record = session.run(
                    """
                    MERGE (c:Collection {id: $collection_id})
                    ON CREATE SET
                        c.name = $name,
                        c.description = $description,
                        c.created_at = datetime().epochMillis
                    ON MATCH SET
                        c.name = coalesce($name, c.name),
                        c.description = coalesce($description, c.description),
                        c.updated_at = datetime().epochMillis
                    RETURN c.id AS id, c.name AS name, c.description AS description
                    """,
                    collection_id=collection_id,
                    name=(name or collection_id.replace("_", " ")).strip() or collection_id,
                    description=description or "",
                ).single()
                return dict(record) if record else {"id": collection_id, "name": collection_id}
        except Exception:
            logger.warning("Graphiti collection metadata is unavailable; continuing without Neo4j metadata writes.", exc_info=True)
            return {"id": collection_id, "name": (name or collection_id.replace("_", " ")).strip() or collection_id}

    def list_collections(self) -> list[dict[str, Any]]:
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(
                    "MATCH (c:Collection) RETURN c.id AS id, c.name AS name, c.description AS description ORDER BY c.name"
                ))
                return [dict(record) for record in records]
        except Exception:
            logger.warning("Could not list Graphiti collection metadata; returning empty list.", exc_info=True)
            return []

    def get_summary(self) -> list[dict[str, Any]]:
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(
                    "MATCH (d:Document) RETURN d.id AS document_id, d.document_name AS document_name, d.collection_id AS collection_id, d.content_hash AS content_hash, d.revision AS revision ORDER BY d.document_name"
                ))
                return [dict(record) for record in records]
        except Exception:
            logger.warning("Could not read Graphiti document summary; returning empty list.", exc_info=True)
            return []

    def _document_hash_key(self, document_name: str, text: str | None = None, collection_id: str = "default") -> str:
        identity = f"{collection_id}|{document_name}|{text or ''}".encode("utf-8")
        return hashlib.sha256(identity).hexdigest()[:24]

    def find_document_by_content_hash(self, content_hash: str, collection_id: str | None = None) -> dict[str, Any] | None:
        if not self.supports_live_metadata:
            return None
        try:
            with self.neo4j_driver.session() as session:
                record = session.run(
                    "MATCH (d:Document) WHERE d.content_hash = $content_hash AND ($collection_id IS NULL OR d.collection_id = $collection_id) RETURN d ORDER BY d.created_at LIMIT 1",
                    content_hash=content_hash,
                    collection_id=normalize_group_id(collection_id or "default"),
                ).single()
                if record is None:
                    return None
                doc = record[0]
                return {key: doc.get(key) for key in ["id", "document_name", "collection_id", "content_hash", "revision"] if key in doc}
        except Exception:
            logger.warning("Graphiti document lookup could not inspect Neo4j metadata; continuing without duplicate detection.", exc_info=True)
            return None

    def _store_document_and_passages(self, *, document_name: str, document_id: str, collection_id: str, content_hash: str, passages: list[dict[str, Any]]) -> None:
        if not self.supports_live_metadata:
            return
        try:
            with self.neo4j_driver.session() as session:
                session.run(
                    """
                    MERGE (d:Document {id: $document_id})
                    ON CREATE SET
                        d.document_name = $document_name,
                        d.collection_id = $collection_id,
                        d.content_hash = $content_hash,
                        d.revision = 1,
                        d.created_at = datetime().epochMillis
                    ON MATCH SET
                        d.document_name = $document_name,
                        d.collection_id = $collection_id,
                        d.content_hash = $content_hash,
                        d.updated_at = datetime().epochMillis
                    WITH d
                    OPTIONAL MATCH (c:Collection {id: $collection_id})
                    MERGE (c)-[:HAS_DOCUMENT]->(d)
                    """,
                    document_id=document_id,
                    document_name=document_name,
                    collection_id=collection_id,
                    content_hash=content_hash,
                )

                for passage in passages:
                    session.run(
                        """
                        MERGE (p:Passage {id: $passage_id})
                        ON CREATE SET
                            p.document_id = $document_id,
                            p.document_name = $document_name,
                            p.collection_id = $collection_id,
                            p.chunk_index = $chunk_index,
                            p.page = $page,
                            p.text = $text,
                            p.content_hash = $content_hash,
                            p.start_offset = $start_offset,
                            p.end_offset = $end_offset,
                            p.created_at = datetime().epochMillis
                        WITH p
                        MATCH (d:Document {id: $document_id})
                        MERGE (d)-[:HAS_PASSAGE]->(p)
                        """,
                        passage_id=passage["passage_id"],
                        document_id=document_id,
                        document_name=document_name,
                        collection_id=collection_id,
                        chunk_index=passage.get("chunk_index", 0),
                        page=passage.get("page"),
                        text=passage.get("text", ""),
                        content_hash=content_hash,
                        start_offset=passage.get("start_offset"),
                        end_offset=passage.get("end_offset"),
                    )
        except Exception:
            logger.warning("Graphiti document metadata could not be stored in Neo4j; continuing with the Graphiti episode pipeline only.", exc_info=True)

    def ingest_document_text(
        self,
        document_name: str,
        text: str,
        *,
        collection_id: str | None = None,
        collection_name: str | None = None,
        document_id: str | None = None,
        store: GraphRAGStore | None = None,
    ) -> dict[str, Any]:
        if not isinstance(document_name, str) or not document_name.strip():
            raise ValueError("Document name is required.")
        cleaned = clean_text(text or "")
        if not cleaned:
            raise ValueError("Document text is empty after cleaning.")

        collection_id = normalize_group_id(collection_id or "default")
        self.ensure_collection(collection_id, name=collection_name or collection_id)

        content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        existing_doc = self.find_document_by_content_hash(content_hash, collection_id)
        if existing_doc:
            logger.info("Document %s already ingested for collection %s; reusing Graphiti episode membership.", document_name, collection_id)
            existing_graph = self.get_graph_data(collection_id=collection_id)
            return {
                "document_name": document_name,
                "document_id": existing_doc.get("document_id") or existing_doc.get("id"),
                "collection_id": collection_id,
                "reused": True,
                "message": f"Document '{document_name}' already exists in collection '{collection_id}'. Reusing the existing Graphiti graph.",
                "passages": 0,
                "entities": len(existing_graph.get("nodes", [])),
                "relationships": len(existing_graph.get("edges", [])),
                "graph": existing_graph,
            }

        chunks = chunk_text(cleaned, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
        if not chunks:
            raise ValueError("No chunks could be created from the provided document text.")

        doc_id = document_id or self._document_hash_key(document_name, cleaned, collection_id)
        passage_rows: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            passage_id = hashlib.sha256(f"{collection_id}|{document_name}|{index}|{chunk}".encode("utf-8")).hexdigest()[:24]
            passage_rows.append({
                "passage_id": passage_id,
                "document_id": doc_id,
                "document_name": document_name,
                "collection_id": collection_id,
                "chunk_index": index,
                "page": None,
                "start_offset": index * max(1, config.chunk_size - config.chunk_overlap),
                "end_offset": (index + 1) * max(1, config.chunk_size - config.chunk_overlap),
                "text": chunk,
                "content_hash": content_hash,
            })

        self._store_document_and_passages(
            document_name=document_name,
            document_id=doc_id,
            collection_id=collection_id,
            content_hash=content_hash,
            passages=passage_rows,
        )

        for index, chunk in enumerate(chunks):
            passage = passage_rows[index]
            episode_name = f"{document_name}#{index}"
            self.graphiti.add_episode(
                name=episode_name,
                episode_body=chunk,
                source_description=(
                    f"Document '{document_name}' in collection '{collection_id}' "
                    f"(chunk {index + 1}/{len(chunks)}, passage_id={passage['passage_id']}, document_id={doc_id})"
                ),
                reference_time=datetime.now(timezone.utc),
                group_id=collection_id,
                source=EpisodeType.message,
                uuid=passage["passage_id"],
            )

        collection_graph = self.get_graph_data(collection_id=collection_id)
        return {
            "document_name": document_name,
            "document_id": doc_id,
            "collection_id": collection_id,
            "reused": False,
            "passages": len(passage_rows),
            "entities": len(collection_graph.get("nodes", [])),
            "relationships": len(collection_graph.get("edges", [])),
            "graph": collection_graph,
        }

    def _resolve_node_name(self, uuid: str | None) -> str:
        if not uuid:
            return "unknown"
        with self.neo4j_driver.session() as session:
            record = session.run("MATCH (n) WHERE n.uuid = $uuid RETURN n.name AS name, labels(n) AS labels LIMIT 1", uuid=str(uuid)).single()
            if record is None:
                return str(uuid)
            return record["name"] or (record["labels"][0] if record.get("labels") else str(uuid))

    def search(self, query: str, *, collection_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query must not be empty.")
        group_ids = [normalize_group_id(collection_id)] if collection_id else None
        search_results = self.graphiti.search(query.strip(), group_ids=group_ids, num_results=limit)
        edges: list[dict[str, Any]] = []
        for item in search_results:
            source_name = self._resolve_node_name(getattr(item, "source_node_uuid", None))
            target_name = self._resolve_node_name(getattr(item, "target_node_uuid", None))
            edges.append({
                "source": source_name,
                "target": target_name,
                "relation": getattr(item, "name", "related_to"),
                "evidence": getattr(item, "fact", "") or getattr(item, "summary", ""),
                "confidence": 0.85,
                "status": "verified",
                "documentName": "",
                "passageId": "",
            })
        return edges

    def get_graph_data(
        self,
        documents: list[str] | None = None,
        collection_id: str | None = None,
        community_id: int | None = None,
        document_name: str | None = None,
    ) -> dict[str, Any]:
        collection_id = normalize_group_id(collection_id or "default") if collection_id else None
        where_clause = ""
        params: dict[str, Any] = {}
        if collection_id:
            where_clause = "WHERE coalesce(n.group_id, n.collection_id) = $collection_id OR coalesce(m.group_id, m.collection_id) = $collection_id"
            params["collection_id"] = collection_id
        if document_name:
            if not where_clause:
                where_clause = "WHERE $document_name IN coalesce(n.document_name, m.document_name)"
            else:
                where_clause += " AND ($document_name IN coalesce(n.document_name, m.document_name) OR $document_name IN coalesce(m.document_name, n.document_name))"
            params["document_name"] = document_name

        query = f"""
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        {where_clause}
        RETURN DISTINCT n, r, m
        """
        if not where_clause:
            query = "MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN DISTINCT n, r, m"

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(query, **params))
        except Exception:
            logger.warning("Graphiti graph query failed; returning an empty graph payload.", exc_info=True)
            return {"nodes": [], "edges": []}

        for record in records:
            left = record.get("n")
            rel = record.get("r")
            right = record.get("m")
            if left is not None:
                node_key = left.get("uuid") or left.get("id") or left.get("name") or str(left.id)
                node_name = left.get("name") or left.get("document_name") or left.get("id") or str(node_key)
                node_type = next(iter(left.labels), "Node") if hasattr(left, "labels") else "Node"
                nodes[node_key] = {
                    "id": node_key,
                    "label": node_name,
                    "type": node_type,
                    "documents": [left.get("document_name")] if left.get("document_name") else [],
                    "collection_id": left.get("collection_id") or left.get("group_id"),
                }
            if right is not None:
                right_key = right.get("uuid") or right.get("id") or right.get("name") or str(right.id)
                right_name = right.get("name") or right.get("document_name") or right.get("id") or str(right_key)
                right_type = next(iter(right.labels), "Node") if hasattr(right, "labels") else "Node"
                nodes[right_key] = {
                    "id": right_key,
                    "label": right_name,
                    "type": right_type,
                    "documents": [right.get("document_name")] if right.get("document_name") else [],
                    "collection_id": right.get("collection_id") or right.get("group_id"),
                }
            if rel is not None and left is not None and right is not None:
                source_id = left.get("uuid") or left.get("id") or left.get("name") or str(left.id)
                target_id = right.get("uuid") or right.get("id") or right.get("name") or str(right.id)
                edges.append({
                    "id": f"{source_id}->{target_id}:{rel.type}",
                    "source": source_id,
                    "target": target_id,
                    "label": rel.type,
                    "evidence_records": [{"evidence": rel.get("fact") or rel.get("summary") or rel.get("name") or ""}],
                    "document_names": [left.get("document_name") or right.get("document_name")],
                    "passage_ids": [],
                })

        return {"nodes": list(nodes.values()), "edges": edges}


adapter = GraphitiAdapter()
