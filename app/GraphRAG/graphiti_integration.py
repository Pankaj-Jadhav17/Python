from __future__ import annotations

import asyncio
import hashlib
import logging
import math
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
    from graphiti_core.llm_client import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.search.search_config import SearchConfig
    from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
except ImportError:  # pragma: no cover
    Graphiti = None
    OpenAIRerankerClient = None
    OpenAIEmbedder = None
    OpenAIEmbedderConfig = None
    EpisodeType = None
    LLMConfig = None
    OpenAIGenericClient = None
    SearchConfig = None
    COMBINED_HYBRID_SEARCH_RRF = None


def normalize_group_id(value: str | None, *, default: str = "default") -> str:
    if not value or not str(value).strip():
        return default
    cleaned = str(value).strip()
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", cleaned)
    normalized = normalized.strip("_")
    normalized = normalized.lower()
    return normalized or default


_SHARED_GRAPHITI_ADAPTER: GraphitiAdapter | None = None


class GraphitiAdapter:
    """Compatibility layer that keeps the app’s contracts while routing graph work through Graphiti."""

    def __init__(self, graphiti: Any | None = None):
        self._graphiti = graphiti
        self._neo4j_driver = None

    async def initialize(self) -> None:
        if self._graphiti is None:
            self._graphiti = self._build_graphiti()
        if getattr(self._graphiti, "build_indices_and_constraints", None) is not None:
            await self._maybe_await(self._graphiti.build_indices_and_constraints())

    async def close(self) -> None:
        if self._graphiti is not None and hasattr(self._graphiti, "close"):
            await self._maybe_await(self._graphiti.close())
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                logger.warning("Graphiti Neo4j driver could not be closed cleanly.", exc_info=True)
            self._neo4j_driver = None

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if asyncio.iscoroutine(value):
            return await value
        if asyncio.isfuture(value):
            return await value
        return value

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

        llm_client = OpenAIGenericClient(config=llm_config)
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

    async def ingest_document_text_async(
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
        existing_doc = None
        if store is not None and hasattr(store, "find_document_by_content_hash"):
            existing_doc = store.find_document_by_content_hash(content_hash, collection_id=collection_id)
        if existing_doc is None and (store is None or not hasattr(store, "find_document_by_content_hash")):
            existing_doc = self.find_document_by_content_hash(content_hash, collection_id)
        if existing_doc:
            logger.info("Document %s already ingested for collection %s; reusing Graphiti episode membership.", document_name, collection_id)
            existing_graph = self.get_graph_data(collection_id=collection_id)
            return {
                "document_name": document_name,
                "document_id": existing_doc.get("document_id") or existing_doc.get("id"),
                "collection_id": collection_id,
                "reused": True,
                "message": f"Reused existing graph for '{document_name}' in collection '{collection_id}'.",
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
            await self._maybe_await(
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
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.ingest_document_text_async(
                    document_name,
                    text,
                    collection_id=collection_id,
                    collection_name=collection_name,
                    document_id=document_id,
                    store=store,
                )
            )
        return self.ingest_document_text_async(
            document_name,
            text,
            collection_id=collection_id,
            collection_name=collection_name,
            document_id=document_id,
            store=store,
        )

    def _resolve_node_name(self, uuid: str | None) -> str:
        if not uuid:
            return "unknown"
        with self.neo4j_driver.session() as session:
            record = session.run("MATCH (n) WHERE n.uuid = $uuid RETURN n.name AS name, labels(n) AS labels LIMIT 1", uuid=str(uuid)).single()
            if record is None:
                return str(uuid)
            return record["name"] or (record["labels"][0] if record.get("labels") else str(uuid))

    def get_passages_by_ids(
        self,
        passage_ids: list[str],
        *,
        collection_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Batch-retrieve Passage nodes and their Document metadata in a single collection-scoped query."""
        if not passage_ids or not self.supports_live_metadata:
            return {}
        cleaned_ids = [str(pid) for pid in passage_ids if pid and str(pid).strip()]
        if not cleaned_ids:
            return {}

        cid = normalize_group_id(collection_id, default="default") if collection_id else None
        query = """
        MATCH (p:Passage)
        WHERE p.id IN $passage_ids AND ($collection_id IS NULL OR p.collection_id = $collection_id)
        OPTIONAL MATCH (d:Document {id: p.document_id})
        RETURN p.id AS passage_id,
               p.document_id AS document_id,
               coalesce(p.document_name, d.document_name, "") AS document_name,
               p.collection_id AS collection_id,
               p.chunk_index AS chunk_index,
               p.page AS page,
               p.text AS text,
               p.content_hash AS content_hash
        """
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(query, passage_ids=cleaned_ids, collection_id=cid))
                return {r["passage_id"]: dict(r) for r in records if r.get("passage_id")}
        except Exception:
            logger.warning("Graphiti passage metadata batch lookup failed; continuing without Neo4j passage metadata.", exc_info=True)
            return {}

    async def search_async(self, query: str, *, collection_id: str | None = None, limit: int = 10) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query must not be empty.")
        norm_collection_id = normalize_group_id(collection_id) if collection_id else None
        group_ids = [norm_collection_id] if norm_collection_id else None
        search_fn = getattr(self.graphiti, "search_", None) or getattr(self.graphiti, "search", None)
        if search_fn is None:
            raise RuntimeError("Graphiti client does not support search operations.")

        if hasattr(self.graphiti, "search_"):
            if COMBINED_HYBRID_SEARCH_RRF is not None:
                search_config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True)
                search_config.limit = limit
            elif SearchConfig is not None:
                search_config = SearchConfig(limit=limit)
            else:
                search_config = None

            if search_config is not None:
                results = await self._maybe_await(
                    search_fn(query.strip(), group_ids=group_ids, config=search_config)
                )
            else:
                results = await self._maybe_await(search_fn(query.strip(), group_ids=group_ids))
        else:
            results = await self._maybe_await(search_fn(query.strip(), group_ids=group_ids, num_results=limit))

        def _get_val(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        def _prop(item: Any, *keys: str, default: Any = None) -> Any:
            for k in keys:
                if isinstance(item, dict):
                    val = item.get(k)
                else:
                    val = getattr(item, k, None)
                if val is not None:
                    return val
            return default

        raw_edges = _get_val(results, "edges", []) or []
        edge_scores = _get_val(results, "edge_reranker_scores", []) or []
        raw_nodes = _get_val(results, "nodes", []) or []
        node_scores = _get_val(results, "node_reranker_scores", []) or []
        raw_episodes = _get_val(results, "episodes", []) or []
        episode_scores = _get_val(results, "episode_reranker_scores", []) or []
        raw_communities = _get_val(results, "communities", []) or []
        comm_scores = _get_val(results, "community_reranker_scores", []) or []

        # 1. Format Nodes
        nodes_dict: dict[str, dict[str, Any]] = {}
        formatted_nodes: list[dict[str, Any]] = []
        for idx, node in enumerate(raw_nodes):
            uuid_val = str(_prop(node, "uuid", "id", default="") or "")
            name_val = str(_prop(node, "name", "label", default="") or "")
            labels = _prop(node, "labels", default=None) or ["Entity"]
            node_type = labels[0] if labels else "Entity"
            score_val = node_scores[idx] if idx < len(node_scores) else _prop(node, "score")
            summary_val = str(_prop(node, "summary", default="") or "")
            formatted_node = {
                "id": uuid_val or name_val,
                "uuid": uuid_val,
                "name": name_val,
                "label": name_val or summary_val or uuid_val,
                "type": node_type,
                "summary": summary_val,
                "group_id": _prop(node, "group_id", default=norm_collection_id),
                "score": score_val,
            }
            formatted_nodes.append(formatted_node)
            if uuid_val:
                nodes_dict[uuid_val] = formatted_node
            elif name_val:
                nodes_dict[name_val] = formatted_node

        # 2. Format Communities
        formatted_communities: list[dict[str, Any]] = []
        for idx, comm in enumerate(raw_communities):
            comm_uuid = str(_prop(comm, "uuid", "id", default="") or "")
            name_val = str(_prop(comm, "name", default="") or "")
            score_val = comm_scores[idx] if idx < len(comm_scores) else _prop(comm, "score")
            formatted_communities.append({
                "id": comm_uuid or name_val,
                "uuid": comm_uuid,
                "name": name_val,
                "summary": str(_prop(comm, "summary", default="") or ""),
                "score": score_val,
                "group_id": _prop(comm, "group_id", default=norm_collection_id),
            })

        # 3. Format Episodes
        formatted_episodes: list[dict[str, Any]] = []
        episodes_by_uuid: dict[str, dict[str, Any]] = {}
        for idx, ep in enumerate(raw_episodes):
            ep_uuid = str(_prop(ep, "uuid", "id", "passage_id", default="") or "")
            if not ep_uuid:
                ep_uuid = f"episode-{idx}"
            score_val = episode_scores[idx] if idx < len(episode_scores) else _prop(ep, "score")
            content_val = str(_prop(ep, "content", "body", "episode_body", "text", default="") or "")
            source_desc = str(_prop(ep, "source_description", "description", default="") or "")
            name_val = str(_prop(ep, "name", "title", default="") or "")
            ep_item = {
                "uuid": ep_uuid,
                "name": name_val,
                "content": content_val,
                "source_description": source_desc,
                "score": score_val,
                "group_id": _prop(ep, "group_id", "collection_id", default=norm_collection_id),
            }
            formatted_episodes.append(ep_item)
            if ep_uuid:
                episodes_by_uuid[ep_uuid] = ep_item

        # 4. Format Edges and collect episode UUIDs
        all_episode_uuids: set[str] = set(episodes_by_uuid.keys())
        formatted_edges: list[dict[str, Any]] = []

        for idx, edge in enumerate(raw_edges):
            edge_uuid = str(_prop(edge, "uuid", "id", default="") or "")
            source_uuid = _prop(edge, "source_node_uuid", "source", default=None)
            target_uuid = _prop(edge, "target_node_uuid", "target", default=None)

            if str(source_uuid) in nodes_dict:
                source_name = nodes_dict[str(source_uuid)]["name"]
            elif source_uuid:
                source_name = self._resolve_node_name(source_uuid)
            else:
                source_name = "unknown"

            if str(target_uuid) in nodes_dict:
                target_name = nodes_dict[str(target_uuid)]["name"]
            elif target_uuid:
                target_name = self._resolve_node_name(target_uuid)
            else:
                target_name = "unknown"

            score_val = edge_scores[idx] if idx < len(edge_scores) else _prop(edge, "score")
            fact_text = str(_prop(edge, "fact", "summary", "evidence", default="") or "")
            relation_val = str(_prop(edge, "name", "relation", "label", default="related_to") or "related_to")

            raw_edge_eps = _prop(edge, "episodes", "passage_ids", default=[]) or []
            if isinstance(raw_edge_eps, list):
                edge_episodes = [str(ep) for ep in raw_edge_eps if ep]
            elif raw_edge_eps:
                edge_episodes = [str(raw_edge_eps)]
            else:
                edge_episodes = []

            for ep_id in edge_episodes:
                all_episode_uuids.add(ep_id)

            formatted_edges.append({
                "id": edge_uuid or f"{source_name}->{target_name}:{relation_val}",
                "uuid": edge_uuid,
                "source": source_name,
                "target": target_name,
                "relation": relation_val,
                "evidence": fact_text,
                "confidence": _prop(edge, "confidence", default=0.0) or 0.0,
                "score": score_val,
                "status": "verified" if fact_text else "unknown",
                "episodes": edge_episodes,
                "passage_ids": edge_episodes,
                "collection_id": _prop(edge, "group_id", "collection_id", default=norm_collection_id),
            })

        # 5. Batch-retrieve Passage metadata for all collected episode UUIDs
        passage_metadata = self.get_passages_by_ids(list(all_episode_uuids), collection_id=norm_collection_id)

        # 6. Build passage evidence items connected with original document metadata
        retrieved_passages: list[dict[str, Any]] = []
        seen_passage_ids: set[str] = set()

        for idx, ep in enumerate(formatted_episodes):
            p_id = ep["uuid"]
            meta = passage_metadata.get(p_id, {})
            doc_name = meta.get("document_name") or ""
            if not doc_name and ep.get("source_description"):
                m = re.search(r"Document '([^']+)'", ep["source_description"])
                if m:
                    doc_name = m.group(1)
            passage_text = meta.get("text") or ep.get("content") or ""
            page_val = meta.get("page")

            # Preserves original episode content even if passage metadata lookup fails
            if passage_text.strip():
                dedup_key = p_id or f"ep-{idx}"
                if dedup_key not in seen_passage_ids:
                    seen_passage_ids.add(dedup_key)
                    retrieved_passages.append({
                        "passage_id": p_id,
                        "passageId": p_id,
                        "episode_id": p_id,
                        "document_id": meta.get("document_id") or "",
                        "document_name": doc_name,
                        "documentName": doc_name,
                        "collection_id": meta.get("collection_id") or ep.get("group_id") or norm_collection_id,
                        "text": passage_text,
                        "evidence": passage_text,
                        "chunk_index": meta.get("chunk_index"),
                        "page": page_val,
                        "score": ep.get("score"),
                    })

        # Attach metadata to edges and preserve multiple supporting episodes
        for edge_item in formatted_edges:
            edge_records: list[dict[str, Any]] = []
            for ep_id in edge_item["episodes"]:
                meta = passage_metadata.get(ep_id, {})
                ep_content = episodes_by_uuid.get(ep_id, {}).get("content", "")
                p_text = meta.get("text") or ep_content or edge_item["evidence"]
                doc_name = meta.get("document_name") or ""
                if not doc_name and ep_id in episodes_by_uuid:
                    m = re.search(r"Document '([^']+)'", episodes_by_uuid[ep_id].get("source_description", ""))
                    if m:
                        doc_name = m.group(1)
                page_val = meta.get("page")
                rec = {
                    "passage_id": ep_id,
                    "passageId": ep_id,
                    "document_name": doc_name,
                    "documentName": doc_name,
                    "page": page_val,
                    "evidence": p_text,
                    "text": p_text,
                    "confidence": edge_item.get("confidence", 0.0),
                    "status": edge_item.get("status", "unknown"),
                }
                edge_records.append(rec)
                if ep_id and ep_id not in seen_passage_ids and p_text.strip():
                    seen_passage_ids.add(ep_id)
                    retrieved_passages.append({
                        "passage_id": ep_id,
                        "passageId": ep_id,
                        "episode_id": ep_id,
                        "document_id": meta.get("document_id") or "",
                        "document_name": doc_name,
                        "documentName": doc_name,
                        "collection_id": meta.get("collection_id") or norm_collection_id,
                        "text": p_text,
                        "evidence": p_text,
                        "chunk_index": meta.get("chunk_index"),
                        "page": page_val,
                        "score": edge_item.get("score"),
                    })

            edge_item["evidence_records"] = edge_records
            edge_item["document_names"] = list({r["document_name"] for r in edge_records if r.get("document_name")})
            if edge_records and not edge_item.get("documentName"):
                edge_item["documentName"] = edge_records[0].get("document_name")
            if edge_records and edge_item.get("page") is None:
                edge_item["page"] = edge_records[0].get("page")
            if edge_records and not edge_item.get("passageId"):
                edge_item["passageId"] = edge_records[0].get("passage_id")

        # 7. Merge any pre-retrieved passages present in results
        results_passages = _get_val(results, "passages", []) or []
        for rp in results_passages:
            p_id = str(_prop(rp, "passage_id", "passageId", "episode_id", default="") or "")
            p_text = str(_prop(rp, "text", "evidence", default="") or "")
            if not p_text.strip():
                continue
            dedup_key = p_id or f"raw-pass-{len(retrieved_passages)}"
            if dedup_key not in seen_passage_ids:
                seen_passage_ids.add(dedup_key)
                doc_n = str(_prop(rp, "document_name", "documentName", default="") or "")
                retrieved_passages.append({
                    "passage_id": p_id,
                    "passageId": p_id,
                    "episode_id": p_id,
                    "document_id": str(_prop(rp, "document_id", default="") or ""),
                    "document_name": doc_n,
                    "documentName": doc_n,
                    "collection_id": _prop(rp, "collection_id", default=norm_collection_id),
                    "text": p_text,
                    "evidence": p_text,
                    "chunk_index": _prop(rp, "chunk_index"),
                    "page": _prop(rp, "page"),
                    "score": _prop(rp, "score"),
                })

        # 8. If Graphiti returned no episodes or passages, query stored collection passages from Neo4j
        if not retrieved_passages and not formatted_episodes and self.supports_live_metadata:
            try:
                passages_from_db = self._search_passages_in_neo4j(query, collection_id=norm_collection_id, limit=limit)
                for p_item in passages_from_db:
                    pid = p_item.get("passage_id")
                    if pid and pid not in seen_passage_ids:
                        seen_passage_ids.add(pid)
                        retrieved_passages.append(p_item)

                if retrieved_passages and not formatted_edges:
                    pids = [p["passage_id"] for p in retrieved_passages if p.get("passage_id")]
                    extra_edges, extra_nodes = self._find_connected_graph_for_passages(pids, collection_id=norm_collection_id)
                    formatted_edges.extend(extra_edges)
                    for n in extra_nodes:
                        if n["id"] not in nodes_dict:
                            nodes_dict[n["id"]] = n
                            formatted_nodes.append(n)
            except Exception:
                logger.warning("Fallback passage retrieval from Neo4j encountered an error; continuing.", exc_info=True)

        return {
            "edges": formatted_edges,
            "nodes": formatted_nodes,
            "episodes": formatted_episodes,
            "communities": formatted_communities,
            "passages": retrieved_passages,
        }

    def _search_passages_in_neo4j(
        self,
        query: str,
        *,
        collection_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search Neo4j Passage nodes for a collection using vector cosine similarity or text overlap."""
        if not self.supports_live_metadata:
            return []
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(
                    """
                    MATCH (p:Passage)
                    WHERE ($collection_id IS NULL OR p.collection_id = $collection_id)
                    RETURN p.id AS passage_id,
                           p.document_id AS document_id,
                           p.document_name AS document_name,
                           p.collection_id AS collection_id,
                           p.chunk_index AS chunk_index,
                           p.page AS page,
                           p.text AS text,
                           p.embedding AS embedding
                    """,
                    collection_id=collection_id,
                ))
        except Exception:
            logger.warning("Could not query passages from Neo4j.", exc_info=True)
            return []

        if not records:
            return []

        scored: list[dict[str, Any]] = []
        q_vec = None
        q_norm = 0.0
        try:
            from .embeddings import embed_question
            q_vec = embed_question(query)
            q_norm = math.sqrt(sum(v * v for v in q_vec))
        except Exception:
            q_vec = None
            q_norm = 0.0

        q_lower = query.lower()
        q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2]

        for record in records:
            r = dict(record)
            p_text = r.get("text") or ""
            if not p_text.strip():
                continue

            p_vec = r.pop("embedding", None)
            if q_vec and p_vec and len(p_vec) == len(q_vec) and q_norm > 0:
                dot = sum(a * b for a, b in zip(q_vec, p_vec))
                p_norm = math.sqrt(sum(v * v for v in p_vec))
                score = dot / (q_norm * p_norm) if (q_norm * p_norm) > 0 else 0.0
            else:
                p_lower = p_text.lower()
                matches = sum(1 for w in q_words if w in p_lower)
                score = (matches / len(q_words)) if q_words else 0.0

            scored.append({
                "passage_id": r["passage_id"],
                "passageId": r["passage_id"],
                "episode_id": r["passage_id"],
                "document_id": r.get("document_id") or "",
                "document_name": r.get("document_name") or "",
                "documentName": r.get("document_name") or "",
                "collection_id": r.get("collection_id") or collection_id,
                "text": p_text,
                "evidence": p_text,
                "chunk_index": r.get("chunk_index"),
                "page": r.get("page"),
                "score": score,
            })

        scored.sort(reverse=True, key=lambda x: x["score"])
        return scored[:limit]

    def _find_connected_graph_for_passages(
        self,
        passage_ids: list[str],
        *,
        collection_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Find connected Concept nodes and RELATES edges in Neo4j for retrieved passages."""
        if not passage_ids or not self.supports_live_metadata:
            return [], []
        edges: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        try:
            with self.neo4j_driver.session() as session:
                records = list(session.run(
                    """
                    MATCH (p:Passage)-[:MENTIONS]->(c:Concept)
                    WHERE p.id IN $passage_ids
                    MATCH (c)-[r:RELATES]->(target:Concept)
                    WHERE ($collection_id IS NULL OR r.collection_id = $collection_id)
                    RETURN c.canonical_name AS source,
                           target.canonical_name AS target,
                           coalesce(r.relation, 'related_to') AS relation,
                           coalesce(r.evidence, '') AS evidence,
                           r.confidence AS confidence,
                           r.document_name AS document_name,
                           r.page AS page,
                           r.passage_ids AS passage_ids
                    LIMIT 20
                    """,
                    passage_ids=passage_ids,
                    collection_id=collection_id,
                ))
                for row in records:
                    src = row.get("source")
                    tgt = row.get("target")
                    if src and tgt:
                        edge = {
                            "id": f"{src}->{tgt}:{row.get('relation')}",
                            "source": src,
                            "target": tgt,
                            "relation": row.get("relation"),
                            "evidence": row.get("evidence"),
                            "confidence": row.get("confidence") or 0.0,
                            "episodes": row.get("passage_ids") or [],
                            "passage_ids": row.get("passage_ids") or [],
                            "documentName": row.get("document_name") or "",
                            "document_name": row.get("document_name") or "",
                            "page": row.get("page"),
                            "evidence_records": [{
                                "evidence": row.get("evidence") or "",
                                "document_name": row.get("document_name") or "",
                                "page": row.get("page"),
                                "confidence": row.get("confidence") or 0.0,
                            }],
                        }
                        edges.append(edge)
                    for n_name in (src, tgt):
                        if n_name and n_name not in seen_nodes:
                            seen_nodes.add(n_name)
                            nodes.append({
                                "id": n_name,
                                "name": n_name,
                                "label": n_name,
                                "type": "Concept",
                            })
        except Exception:
            logger.warning("Could not query connected concepts in Neo4j; continuing with empty edges.", exc_info=True)
        return edges, nodes

    def search(self, query: str, *, collection_id: str | None = None, limit: int = 10) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.search_async(query, collection_id=collection_id, limit=limit))
        return self.search_async(query, collection_id=collection_id, limit=limit)

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

        def _extract_id(entity: Any) -> str:
            if entity is None:
                return ""
            return str(getattr(entity, "element_id", None) or getattr(entity, "id", None) or "")

        for record in records:
            left = record.get("n")
            rel = record.get("r")
            right = record.get("m")
            if left is not None:
                node_key = left.get("uuid") or left.get("id") or left.get("name") or _extract_id(left)
                node_name = left.get("name") or left.get("document_name") or left.get("id") or str(node_key)
                node_type = next(iter(left.labels), "Node") if hasattr(left, "labels") and left.labels else "Node"
                nodes[node_key] = {
                    "id": node_key,
                    "label": node_name,
                    "type": node_type,
                    "documents": [left.get("document_name")] if left.get("document_name") else [],
                    "collection_id": left.get("collection_id") or left.get("group_id"),
                }
            if right is not None:
                right_key = right.get("uuid") or right.get("id") or right.get("name") or _extract_id(right)
                right_name = right.get("name") or right.get("document_name") or right.get("id") or str(right_key)
                right_type = next(iter(right.labels), "Node") if hasattr(right, "labels") and right.labels else "Node"
                nodes[right_key] = {
                    "id": right_key,
                    "label": right_name,
                    "type": right_type,
                    "documents": [right.get("document_name")] if right.get("document_name") else [],
                    "collection_id": right.get("collection_id") or right.get("group_id"),
                }
            if rel is not None and left is not None and right is not None:
                source_id = left.get("uuid") or left.get("id") or left.get("name") or _extract_id(left)
                target_id = right.get("uuid") or right.get("id") or right.get("name") or _extract_id(right)
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


def get_shared_graphiti_adapter() -> GraphitiAdapter:
    global _SHARED_GRAPHITI_ADAPTER
    if _SHARED_GRAPHITI_ADAPTER is None:
        _SHARED_GRAPHITI_ADAPTER = GraphitiAdapter()
    return _SHARED_GRAPHITI_ADAPTER


class _SharedAdapterProxy:
    """Proxy providing backward compatibility for module-level `adapter` imports."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_shared_graphiti_adapter(), name)


adapter = _SharedAdapterProxy()
