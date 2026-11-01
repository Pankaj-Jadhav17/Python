from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None

from app.config import config
from .entity_resolution import detect_graph_communities

logger = logging.getLogger(__name__)


class GraphRAGStore:
    """Store and retrieve document passages and knowledge-graph data in Neo4j."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.config = config

        self.uri = uri or self.config.neo4j_uri
        self.user = user or self.config.neo4j_user
        self.password = (
            password
            if password is not None
            else self.config.neo4j_password
        )

        if GraphDatabase is None:
            raise RuntimeError(
                "The neo4j package is required to use GraphRAGStore."
            )

        if not self.password:
            raise RuntimeError(
                "Neo4j password is missing. Set NEO4J_PASSWORD "
                "before starting the application."
            )

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )
        self.ensure_schema()

    def close(self) -> None:
        """Close the Neo4j driver."""
        if getattr(self, "driver", None) is not None:
            self.driver.close()

    @staticmethod
    def _consume_result(result: Any) -> None:
        """Consume a Neo4j result when the driver exposes a consume method."""
        consume = getattr(result, "consume", None)
        if callable(consume):
            consume()

    # ---------------------------------------------------------
    # SCHEMA, CONSTRAINTS & INDEXES
    # ---------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create non-destructive constraints and indexes if they do not exist."""
        if not getattr(self, "driver", None):
            return

        with self.driver.session() as session:
            # Collection ID constraint
            try:
                self._consume_result(
                    session.run(
                        "CREATE CONSTRAINT collection_id_unique IF NOT EXISTS "
                        "FOR (c:Collection) REQUIRE c.id IS UNIQUE"
                    )
                )
            except Exception:
                logger.debug("Collection constraint already exists or not supported.")

            # Document ID index/constraint
            try:
                self._consume_result(
                    session.run(
                        "CREATE INDEX document_id_index IF NOT EXISTS "
                        "FOR (d:Document) ON (d.id)"
                    )
                )
            except Exception:
                logger.debug("Document index already exists or not supported.")

            # Document content hash index for duplicate prevention
            try:
                self._consume_result(
                    session.run(
                        "CREATE INDEX document_content_hash_index IF NOT EXISTS "
                        "FOR (d:Document) ON (d.content_hash)"
                    )
                )
            except Exception:
                logger.debug("Document content_hash index already exists or not supported.")

            # Passage ID index
            try:
                self._consume_result(
                    session.run(
                        "CREATE INDEX passage_id_index IF NOT EXISTS "
                        "FOR (p:Passage) ON (p.id)"
                    )
                )
            except Exception:
                logger.debug("Passage index already exists or not supported.")

            # Concept canonical_id index
            try:
                self._consume_result(
                    session.run(
                        "CREATE INDEX concept_canonical_id_index IF NOT EXISTS "
                        "FOR (c:Concept) ON (c.canonical_id)"
                    )
                )
            except Exception:
                logger.debug("Concept canonical_id index already exists or not supported.")

    # ---------------------------------------------------------
    # VECTOR INDEX
    # ---------------------------------------------------------

    def ensure_vector_index(
        self,
        index_name: str = "passage_embedding_index",
        property_name: str = "embedding",
        dimension: int | None = None,
    ) -> bool:
        """
        Create a Neo4j vector index if necessary.
        Tries modern Neo4j syntax first, then older procedure.
        """
        if not getattr(self, "driver", None):
            raise RuntimeError("Neo4j driver is not available.")

        dimension = dimension or 768

        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", index_name):
            raise ValueError("Invalid vector index name.")

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", property_name):
            raise ValueError("Invalid embedding property name.")

        with self.driver.session() as session:
            try:
                records = list(
                    session.run(
                        """
                        SHOW INDEXES
                        YIELD name, type, state
                        WHERE name = $index_name
                        RETURN name, type, state
                        """,
                        index_name=index_name,
                    )
                )

                if records:
                    record = records[0]
                    if record["state"] == "ONLINE":
                        return record["type"] == "VECTOR"
            except Exception:
                logger.warning("Could not inspect existing Neo4j indexes.", exc_info=True)

            # Modern syntax
            try:
                self._consume_result(
                    session.run(
                        f"""
                        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                        FOR (p:Passage)
                        ON (p.{property_name})
                        OPTIONS {{
                            indexConfig: {{
                                `vector.dimensions`: {dimension},
                                `vector.similarity_function`: 'cosine'
                            }}
                        }}
                        """
                    )
                )
                return True
            except Exception:
                logger.info("Modern vector-index syntax failed; trying legacy procedure.", exc_info=True)

            try:
                self._consume_result(
                    session.run(
                        """
                        CALL db.index.vector.createNodeIndex(
                            $index_name,
                            $label,
                            $property,
                            $dimension,
                            'cosine'
                        )
                        """,
                        index_name=index_name,
                        label="Passage",
                        property=property_name,
                        dimension=dimension,
                    )
                )
                return True
            except Exception:
                logger.warning("Could not create vector index '%s'.", index_name, exc_info=True)
                return False

    # ---------------------------------------------------------
    # COLLECTION MANAGEMENT
    # ---------------------------------------------------------

    def ensure_collection(
        self,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Ensure a Collection node exists and return its metadata."""
        col_id = collection_id.strip() if collection_id else "default"
        display_name = name.strip() if name else col_id.replace("_", " ").title()

        with self.driver.session() as session:
            record = session.run(
                """
                MERGE (c:Collection {id: $collection_id})
                ON CREATE SET
                    c.name = $name,
                    c.description = $description,
                    c.created_at = datetime().epochMillis,
                    c.updated_at = datetime().epochMillis
                ON MATCH SET
                    c.name = coalesce($name, c.name),
                    c.updated_at = datetime().epochMillis
                RETURN c.id AS id, c.name AS name, c.description AS description
                """,
                collection_id=col_id,
                name=display_name,
                description=description or "",
            ).single()

            return dict(record) if record else {"id": col_id, "name": display_name}

    def list_collections(self) -> list[dict[str, Any]]:
        """List all collections with their document, concept, and relationship counts."""
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Collection)
                OPTIONAL MATCH (c)-[:CONTAINS_DOCUMENT]->(d:Document)
                OPTIONAL MATCH (d)-[:HAS_CONCEPT]->(concept:Concept)
                OPTIONAL MATCH (concept)-[r:RELATES]->(:Concept)
                WHERE r.collection_id = c.id
                RETURN c.id AS collection_id,
                       c.name AS name,
                       c.description AS description,
                       COUNT(DISTINCT d) AS document_count,
                       COUNT(DISTINCT concept) AS concept_count,
                       COUNT(DISTINCT r) AS relationship_count
                ORDER BY name
                """
            )
            collections = [dict(record) for record in rows]
            # If no Collection nodes exist yet, provide a default collection entry
            if not collections:
                summary = self.get_graph_summary()
                total_docs = len(summary)
                total_concepts = sum(doc.get("concept_count", 0) for doc in summary)
                total_rels = sum(doc.get("relationship_count", 0) for doc in summary)
                collections = [{
                    "collection_id": "default",
                    "name": "General Collection",
                    "description": "Default collection for uploaded documents.",
                    "document_count": total_docs,
                    "concept_count": total_concepts,
                    "relationship_count": total_rels,
                }]
            return collections

    # ---------------------------------------------------------
    # DUPLICATE INGESTION DETECTION
    # ---------------------------------------------------------

    def find_document_by_content_hash(
        self,
        content_hash: str,
        collection_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an already-processed document matching the exact content SHA-256 hash."""
        if not content_hash:
            return None

        col_id = collection_id or "default"
        with self.driver.session() as session:
            record = session.run(
                """
                MATCH (d:Document {content_hash: $content_hash})
                WHERE ($collection_id IS NULL OR d.collection_id = $collection_id)
                  AND d.status = 'processed'
                RETURN d.id AS document_id,
                       d.name AS document_name,
                       d.content_hash AS content_hash,
                       d.collection_id AS collection_id,
                       d.revision_id AS revision_id,
                       d.status AS status
                LIMIT 1
                """,
                content_hash=content_hash,
                collection_id=col_id,
            ).single()

            return dict(record) if record else None

    # ---------------------------------------------------------
    # DOCUMENT AND PASSAGE STORAGE
    # ---------------------------------------------------------

    def store_document_passages(
        self,
        document_name: str,
        passages: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        collection_id: str | None = None,
        content_hash: str | None = None,
        revision_id: str = "rev-1",
    ) -> None:
        """Store document and passages, linking them to a collection."""
        if not passages:
            return

        col_id = collection_id or "default"
        document_identifier = document_id or document_name

        self.ensure_collection(col_id)

        with self.driver.session() as session:
            # Create Document and connect to Collection
            self._consume_result(
                session.run(
                    """
                    MERGE (c:Collection {id: $collection_id})
                    MERGE (d:Document {id: $document_id})
                    ON CREATE SET
                        d.name = $document_name,
                        d.collection_id = $collection_id,
                        d.content_hash = coalesce($content_hash, d.content_hash),
                        d.revision_id = $revision_id,
                        d.status = 'processed',
                        d.created_at = datetime().epochMillis,
                        d.updated_at = datetime().epochMillis
                    ON MATCH SET
                        d.name = coalesce(d.name, $document_name),
                        d.collection_id = coalesce(d.collection_id, $collection_id),
                        d.content_hash = coalesce($content_hash, d.content_hash),
                        d.revision_id = $revision_id,
                        d.status = 'processed',
                        d.updated_at = datetime().epochMillis
                    MERGE (c)-[:CONTAINS_DOCUMENT]->(d)
                    """,
                    collection_id=col_id,
                    document_name=document_name,
                    document_id=document_identifier,
                    content_hash=content_hash or "",
                    revision_id=revision_id,
                )
            )

            # Store passages
            self._consume_result(
                session.run(
                    """
                    UNWIND $passages AS item

                    MERGE (p:Passage {id: item.passage_id})

                    SET p.embedding = item.embedding,
                        p.text = item.text,
                        p.page = item.page,
                        p.start_offset = item.start_offset,
                        p.end_offset = item.end_offset,
                        p.document_name = $document_name,
                        p.document_id = $document_id,
                        p.collection_id = $collection_id,
                        p.chunk_index = coalesce(item.chunk_index, 0),
                        p.content_hash = item.content_hash

                    WITH p
                    MATCH (d:Document {id: $document_id})
                    MERGE (d)-[:HAS_PASSAGE]->(p)
                    """,
                    collection_id=col_id,
                    document_name=document_name,
                    document_id=document_identifier,
                    passages=passages,
                )
            )

    # ---------------------------------------------------------
    # CANONICAL ENTITY LOOKUP FOR RESOLUTION
    # ---------------------------------------------------------

    def get_canonical_entities(self, collection_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve existing canonical entities for a collection to support resolution."""
        col_id = collection_id or "default"
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Concept)
                WHERE ($collection_id IS NULL AND c.collection_id IS NULL)
                   OR ($collection_id IS NOT NULL AND c.collection_id = $collection_id)
                RETURN coalesce(c.canonical_id, 'concept:' + c.canonical_name) AS canonical_id,
                       c.canonical_name AS canonical_name,
                       coalesce(c.entity_type, 'Concept') AS entity_type,
                       coalesce(c.aliases, []) AS aliases
                """,
                collection_id=col_id,
            )
            return [dict(record) for record in rows]

    # ---------------------------------------------------------
    # CONCEPT AND MULTI-EVIDENCE RELATIONSHIP STORAGE
    # ---------------------------------------------------------

    def store_entities_and_relationships(
        self,
        document_name: str,
        relationships: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        collection_id: str | None = None,
        entity_map: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """
        Store extracted concepts and relationships with full multi-evidence provenance.
        Accumulates multiple evidence sources without overwriting.
        """
        if not relationships:
            return

        col_id = collection_id or "default"
        document_identifier = document_id or document_name
        entities = entity_map or {}

        # Build concepts payload
        concept_names = sorted(
            {
                concept
                for item in relationships
                for concept in (item["subject"], item["object"])
                if concept
            }
        )

        concepts_data = []
        for name in concept_names:
            ent_info = entities.get(name) or {}
            c_id = ent_info.get("canonical_id") or f"c:{col_id}:{name.lower().replace(' ', '_')}"
            c_name = ent_info.get("canonical_name") or name
            c_type = ent_info.get("entity_type") or "Concept"
            c_aliases = ent_info.get("aliases") or [name]
            concepts_data.append({
                "canonical_id": c_id,
                "canonical_name": c_name,
                "normalized_name": name.lower(),
                "entity_type": c_type,
                "aliases": c_aliases,
            })

        # Build relationships payload with serialized evidence record
        rel_payload = []
        for item in relationships:
            subj_info = entities.get(item["subject"]) or {}
            obj_info = entities.get(item["object"]) or {}
            subj_id = subj_info.get("canonical_id") or f"c:{col_id}:{item['subject'].lower().replace(' ', '_')}"
            obj_id = obj_info.get("canonical_id") or f"c:{col_id}:{item['object'].lower().replace(' ', '_')}"

            ev_record = {
                "document_name": document_name,
                "document_id": document_identifier,
                "passage_id": item.get("passage_id"),
                "page": item.get("page"),
                "evidence": item.get("evidence"),
                "confidence": item.get("confidence", 0.8),
                "status": item.get("status", "verified"),
            }

            rel_payload.append({
                "subject_id": subj_id,
                "subject_name": subj_info.get("canonical_name") or item["subject"],
                "object_id": obj_id,
                "object_name": obj_info.get("canonical_name") or item["object"],
                "relation": item["relation"],
                "evidence": item.get("evidence", ""),
                "evidence_json": json.dumps(ev_record),
                "passage_id": item.get("passage_id"),
                "page": item.get("page"),
                "confidence": item.get("confidence", 0.8),
                "status": item.get("status", "verified"),
                "relationship_id": item.get("relationship_id") or f"rel:{subj_id}:{item['relation']}:{obj_id}",
            })

        with self.driver.session() as session:
            # 1. Store/Merge Concepts
            self._consume_result(
                session.run(
                    """
                    MATCH (d:Document {id: $document_id})
                    UNWIND $concepts AS c_item

                    MERGE (c:Concept {canonical_id: c_item.canonical_id})
                    ON CREATE SET
                        c.canonical_name = c_item.canonical_name,
                        c.normalized_name = c_item.normalized_name,
                        c.entity_type = c_item.entity_type,
                        c.collection_id = $collection_id,
                        c.aliases = c_item.aliases
                    ON MATCH SET
                        c.entity_type = CASE WHEN c.entity_type = 'Concept' AND c_item.entity_type <> 'Concept' THEN c_item.entity_type ELSE c.entity_type END,
                        c.aliases = CASE
                            WHEN c.aliases IS NULL THEN c_item.aliases
                            ELSE coalesce(c.aliases, []) + [alias IN coalesce(c_item.aliases, []) WHERE NOT alias IN coalesce(c.aliases, [])]
                        END,
                        c.collection_id = CASE WHEN c.collection_id IS NULL THEN $collection_id ELSE c.collection_id END

                    MERGE (d)-[:HAS_CONCEPT]->(c)
                    """,
                    document_name=document_name,
                    document_id=document_identifier,
                    collection_id=col_id,
                    concepts=concepts_data,
                )
            )

            # 2. Connect Passages to Concepts (MENTIONS)
            self._consume_result(
                session.run(
                    """
                    UNWIND $relationships AS item

                    MATCH (subject:Concept {canonical_id: item.subject_id})
                    MATCH (object:Concept {canonical_id: item.object_id})
                    OPTIONAL MATCH (p:Passage {id: item.passage_id})

                    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
                        MERGE (p)-[:MENTIONS]->(subject)
                        MERGE (p)-[:MENTIONS]->(object)
                    )
                    """,
                    relationships=rel_payload,
                )
            )

            # 3. Store Evidence-Bearing RELATES edges (Accumulate multiple evidence without overwriting)
            self._consume_result(
                session.run(
                    """
                    UNWIND $relationships AS item

                    MATCH (subject:Concept {canonical_id: item.subject_id})
                    MATCH (object:Concept {canonical_id: item.object_id})

                    MERGE (subject)-[r:RELATES {relation: item.relation, collection_id: $collection_id}]->(object)
                    ON CREATE SET
                        r.id = item.relationship_id,
                        r.relation = item.relation,
                        r.evidence = item.evidence,
                        r.evidence_list = [item.evidence],
                        r.evidence_records = [item.evidence_json],
                        r.document_name = $document_name,
                        r.document_names = [$document_name],
                        r.document_id = $document_id,
                        r.passageId = item.passage_id,
                        r.passage_ids = [item.passage_id],
                        r.page = item.page,
                        r.confidence = item.confidence,
                        r.status = coalesce(item.status, 'verified'),
                        r.collection_id = $collection_id,
                        r.model = 'ollama'
                    ON MATCH SET
                        r.evidence = coalesce(r.evidence, item.evidence),
                        r.evidence_list = CASE WHEN item.evidence IN coalesce(r.evidence_list, []) THEN r.evidence_list ELSE coalesce(r.evidence_list, []) + item.evidence END,
                        r.document_names = CASE WHEN $document_name IN coalesce(r.document_names, []) THEN r.document_names ELSE coalesce(r.document_names, []) + $document_name END,
                        r.passage_ids = CASE WHEN item.passage_id IN coalesce(r.passage_ids, []) THEN r.passage_ids ELSE coalesce(r.passage_ids, []) + item.passage_id END,
                        r.evidence_records = coalesce(r.evidence_records, []) + [item.evidence_json],
                        r.confidence = CASE WHEN item.confidence > coalesce(r.confidence, 0.0) THEN item.confidence ELSE r.confidence END
                    """,
                    document_name=document_name,
                    document_id=document_identifier,
                    collection_id=col_id,
                    relationships=rel_payload,
                )
            )

    # ---------------------------------------------------------
    # PASSAGE RETRIEVAL
    # ---------------------------------------------------------

    def search_similar_passages(
        self,
        question_vector: list[float],
        *,
        limit: int | None = None,
        collection_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve passages using vector index with fallback to cosine similarity."""
        limit = limit if limit is not None else self.config.vector_retrieval_count
        if limit <= 0 or not question_vector:
            return []

        col_id = collection_id

        with self.driver.session() as session:
            try:
                results = session.run(
                    """
                    CALL db.index.vector.queryNodes(
                        'passage_embedding_index',
                        $limit,
                        $vector
                    )
                    YIELD node, score
                    WHERE ($collection_id IS NULL OR node.collection_id = $collection_id)
                    RETURN node.id AS passage_id,
                           node.text AS text,
                           node.document_name AS document_name,
                           node.page AS page,
                           node.start_offset AS start_offset,
                           node.end_offset AS end_offset,
                           score AS score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                    vector=question_vector,
                    collection_id=col_id,
                )
                passages = [dict(record) for record in results]
                if passages:
                    return passages
            except Exception:
                logger.warning("Vector-index query failed. Falling back to cosine similarity.", exc_info=True)

            # Fallback: exact cosine similarity
            records = session.run(
                """
                MATCH (p:Passage)
                WHERE p.embedding IS NOT NULL
                  AND ($collection_id IS NULL OR p.collection_id = $collection_id)
                RETURN p.id AS passage_id,
                       p.text AS text,
                       p.document_name AS document_name,
                       p.page AS page,
                       p.start_offset AS start_offset,
                       p.end_offset AS end_offset,
                       p.embedding AS embedding
                """,
                collection_id=col_id,
            )

            scored = []
            q_norm = math.sqrt(sum(v * v for v in question_vector))
            if q_norm == 0:
                return []

            for record in records:
                p = dict(record)
                p_vec = p.pop("embedding", None)
                if not p_vec or len(p_vec) != len(question_vector):
                    continue

                dot = sum(a * b for a, b in zip(question_vector, p_vec))
                p_norm = math.sqrt(sum(v * v for v in p_vec))
                denom = q_norm * p_norm
                score = dot / denom if denom > 0 else 0.0
                p["score"] = score
                scored.append(p)

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:limit]

    # ---------------------------------------------------------
    # GRAPH EXPANSION
    # ---------------------------------------------------------

    def expand_graph(
        self,
        evidence: list[dict[str, Any]],
        *,
        depth: int | None = None,
        collection_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Expand graph relationships from retrieved passages."""
        if not evidence:
            return []

        passage_ids = sorted({item.get("passage_id") for item in evidence if item.get("passage_id")})
        if not passage_ids:
            return []

        depth = depth if depth is not None else self.config.graph_traversal_depth
        max_depth = min(max(1, depth), 5)

        with self.driver.session() as session:
            rows = session.run(
                f"""
                MATCH (p:Passage)-[:MENTIONS]->(c:Concept)
                WHERE p.id IN $passage_ids

                MATCH path = (c)-[rels:RELATES*1..{max_depth}]-(related:Concept)
                WHERE length(rels) <= $depth
                  AND ($collection_id IS NULL OR all(r IN rels WHERE r.collection_id = $collection_id))

                RETURN c.canonical_name AS source,
                       related.canonical_name AS target,
                       [rel IN rels | coalesce(rel.relation, type(rel))] AS relations,
                       [rel IN rels | coalesce(rel.evidence, '')] AS evidence_list,
                       coalesce(p.page, 0) AS page,
                       p.id AS passage_id,
                       coalesce(p.document_name, '') AS document_name

                LIMIT 30
                """,
                passage_ids=passage_ids,
                depth=depth,
                collection_id=collection_id,
            )

            expanded = []
            for record in rows:
                item = dict(record)
                rels = item.pop("relations", [])
                evs = item.pop("evidence_list", [])
                item["relation"] = " -> ".join(rels) if rels else ""
                item["evidence"] = " | ".join(e for e in evs if e)
                expanded.append(item)

            return expanded

    # ---------------------------------------------------------
    # GRAPH DATA FOR VISUALIZATION
    # ---------------------------------------------------------

    def get_graph_data(
        self,
        document_name: str | None = None,
        collection_id: str | None = None,
        community_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Return graph nodes and edges for visualization.
        Supports filtering by document_name, collection_id, or community_id.
        Computes analytical graph community IDs on nodes.
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        def add_node(
            node_id: str,
            label: str,
            node_type: str,
            *,
            entity_type: str | None = None,
            aliases: list[str] | None = None,
            documents: list[str] | None = None,
        ) -> None:
            if node_id not in seen_nodes:
                nodes.append({
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "entity_type": entity_type or node_type,
                    "aliases": aliases or [label],
                    "documents": documents or [],
                })
                seen_nodes.add(node_id)
            else:
                # Append documents if node already seen
                if documents:
                    for n in nodes:
                        if n["id"] == node_id:
                            for doc in documents:
                                if doc not in n["documents"]:
                                    n["documents"].append(doc)
                            break

        with self.driver.session() as session:
            # 1. Retrieve Documents, Passages, and Concepts
            cypher_passages = """
                MATCH (d:Document)
                WHERE ($document_name IS NULL OR d.name = $document_name)
                  AND ($collection_id IS NULL OR d.collection_id = $collection_id)

                OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                OPTIONAL MATCH (p)-[:MENTIONS]->(c:Concept)

                RETURN d.id AS document_id,
                       d.name AS document_name,
                       d.collection_id AS collection_id,
                       p.id AS passage_id,
                       coalesce(c.canonical_id, 'concept:' + c.canonical_name) AS concept_id,
                       c.canonical_name AS concept_name,
                       coalesce(c.entity_type, 'Concept') AS entity_type,
                       coalesce(c.aliases, []) AS aliases
            """

            for row in session.run(cypher_passages, document_name=document_name, collection_id=collection_id):
                doc_id = row.get("document_id")
                doc_name = row.get("document_name")
                passage_id = row.get("passage_id")
                concept_id = row.get("concept_id")
                concept_name = row.get("concept_name")
                entity_type = row.get("entity_type") or "Concept"
                aliases = row.get("aliases") or []
                doc_node_id = f"document:{doc_id}" if doc_id else f"document:{doc_name}"

                if doc_name:
                    add_node(doc_node_id, doc_name, "Document")

                if passage_id:
                    p_node_id = f"passage:{passage_id}"
                    add_node(p_node_id, f"Passage {passage_id[:8]}", "Passage")
                    if doc_name:
                        edge_key = (doc_node_id, p_node_id, "HAS_PASSAGE")
                        if edge_key not in seen_edges:
                            edges.append({
                                "source": doc_node_id,
                                "target": p_node_id,
                                "label": "HAS_PASSAGE",
                            })
                            seen_edges.add(edge_key)

                if concept_id and concept_name:
                    add_node(
                        concept_id,
                        concept_name,
                        "Concept",
                        entity_type=entity_type,
                        aliases=aliases,
                        documents=[doc_name] if doc_name else [],
                    )
                    if doc_name:
                        edge_key = (doc_node_id, concept_id, "HAS_CONCEPT")
                        if edge_key not in seen_edges:
                            edges.append({
                                "source": doc_node_id,
                                "target": concept_id,
                                "label": "HAS_CONCEPT",
                            })
                            seen_edges.add(edge_key)

                    if passage_id:
                        edge_key = (f"passage:{passage_id}", concept_id, "MENTIONS")
                        if edge_key not in seen_edges:
                            edges.append({
                                "source": f"passage:{passage_id}",
                                "target": concept_id,
                                "label": "MENTIONS",
                            })
                            seen_edges.add(edge_key)

            # 2. Retrieve Concept RELATES edges with full evidence provenance
            cypher_relations = """
                MATCH (subject:Concept)-[r:RELATES]->(object:Concept)
                WHERE ($document_name IS NULL OR $document_name IN coalesce(r.document_names, [r.document_name]))
                  AND ($collection_id IS NULL OR r.collection_id = $collection_id)

                RETURN coalesce(subject.canonical_id, 'concept:' + subject.canonical_name) AS subject_id,
                       subject.canonical_name AS subject_name,
                       coalesce(subject.entity_type, 'Concept') AS subject_type,
                       coalesce(subject.aliases, []) AS subject_aliases,
                       coalesce(object.canonical_id, 'concept:' + object.canonical_name) AS object_id,
                       object.canonical_name AS object_name,
                       coalesce(object.entity_type, 'Concept') AS object_type,
                       coalesce(object.aliases, []) AS object_aliases,
                       coalesce(r.relation, type(r)) AS relation,
                       r.evidence AS evidence,
                       coalesce(r.evidence_list, [r.evidence]) AS evidence_list,
                       coalesce(r.evidence_records, []) AS evidence_records,
                       coalesce(r.document_names, [r.document_name]) AS document_names,
                       coalesce(r.passage_ids, [r.passageId]) AS passage_ids,
                       r.page AS page,
                       coalesce(r.confidence, 0.8) AS confidence,
                       coalesce(r.status, 'verified') AS status
            """

            for row in session.run(cypher_relations, document_name=document_name, collection_id=collection_id):
                subj_id = row.get("subject_id")
                subj_name = row.get("subject_name")
                obj_id = row.get("object_id")
                obj_name = row.get("object_name")
                relation = row.get("relation") or "RELATES"

                if not subj_id or not obj_id or not subj_name or not obj_name:
                    continue

                add_node(
                    subj_id,
                    subj_name,
                    "Concept",
                    entity_type=row.get("subject_type"),
                    aliases=row.get("subject_aliases"),
                    documents=row.get("document_names"),
                )
                add_node(
                    obj_id,
                    obj_name,
                    "Concept",
                    entity_type=row.get("object_type"),
                    aliases=row.get("object_aliases"),
                    documents=row.get("document_names"),
                )

                edge_key = (subj_id, obj_id, relation)
                if edge_key not in seen_edges:
                    parsed_records = []
                    for raw_rec in row.get("evidence_records", []):
                        if isinstance(raw_rec, str):
                            try:
                                parsed_records.append(json.loads(raw_rec))
                            except Exception:
                                parsed_records.append({"evidence": raw_rec})
                        elif isinstance(raw_rec, dict):
                            parsed_records.append(raw_rec)

                    edges.append({
                        "source": subj_id,
                        "target": obj_id,
                        "label": relation,
                        "evidence": row.get("evidence"),
                        "evidence_list": [ev for ev in row.get("evidence_list", []) if ev],
                        "evidence_records": parsed_records,
                        "documentName": (row.get("document_names") or [""])[0],
                        "document_names": row.get("document_names") or [],
                        "passageId": (row.get("passage_ids") or [""])[0],
                        "passage_ids": row.get("passage_ids") or [],
                        "page": row.get("page"),
                        "confidence": row.get("confidence"),
                        "status": row.get("status"),
                    })
                    seen_edges.add(edge_key)

        # Apply community detection across concepts
        concept_nodes = [n for n in nodes if n["type"] == "Concept"]
        concept_edges = [
            e for e in edges
            if e.get("label") not in {"HAS_PASSAGE", "HAS_CONCEPT", "MENTIONS"}
        ]
        if concept_nodes and concept_edges:
            communities = detect_graph_communities(concept_nodes, concept_edges)
            for n in nodes:
                if n["id"] in communities:
                    n["community_id"] = communities[n["id"]]

        # Optional community filter
        if community_id is not None:
            filtered_nodes = [n for n in nodes if n.get("community_id") == community_id or n["type"] != "Concept"]
            valid_ids = {n["id"] for n in filtered_nodes}
            filtered_edges = [e for e in edges if e["source"] in valid_ids and e["target"] in valid_ids]
            return {"nodes": filtered_nodes, "edges": filtered_edges, "collection_id": collection_id}

        return {
            "nodes": nodes,
            "edges": edges,
            "collection_id": collection_id,
        }

    # ---------------------------------------------------------
    # GRAPH SUMMARY
    # ---------------------------------------------------------

    def get_graph_summary(self) -> list[dict[str, Any]]:
        """Return passage, concept, and relationship counts for each document."""
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (d:Document)
                OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                OPTIONAL MATCH (d)-[:HAS_CONCEPT]->(c:Concept)
                OPTIONAL MATCH (c)-[r:RELATES]->(:Concept)
                RETURN d.name AS document_name,
                       coalesce(d.collection_id, 'default') AS collection_id,
                       COUNT(DISTINCT p) AS passage_count,
                       COUNT(DISTINCT c) AS concept_count,
                       COUNT(DISTINCT r) AS relationship_count
                ORDER BY document_name
                """
            )
            return [dict(record) for record in rows]
