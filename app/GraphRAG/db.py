import logging
import math
import re

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None

from .config import config


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

    def close(self) -> None:
        """Close the Neo4j driver."""
        if getattr(self, "driver", None) is not None:
            self.driver.close()

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

        Tries modern Neo4j syntax first, then the older procedure.
        Returns True only when the index is reported ONLINE.
        """
        if not getattr(self, "driver", None):
            raise RuntimeError("Neo4j driver is not available.")

        dimension = dimension or 768

        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")

        # These identifiers are interpolated into Cypher, so validate them.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", index_name):
            raise ValueError("Invalid vector index name.")

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", property_name):
            raise ValueError("Invalid embedding property name.")

        with self.driver.session() as session:
            # Check whether the index already exists.
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
                        if record["type"] != "VECTOR":
                            logger.error(
                                "Index '%s' exists but is not a vector index.",
                                index_name,
                            )
                            return False

                        return True

                    logger.warning(
                        "Vector index '%s' exists but is not ONLINE: %s",
                        index_name,
                        record["state"],
                    )

            except Exception:
                logger.warning(
                    "Could not inspect existing Neo4j indexes.",
                    exc_info=True,
                )

            # Modern syntax, supported by recent Neo4j 5.x versions.
            try:
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
                ).consume()

            except Exception:
                logger.info(
                    "Modern vector-index syntax failed; "
                    "trying the legacy procedure.",
                    exc_info=True,
                )

                # Older Neo4j syntax.
                try:
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
                    ).consume()

                except Exception:
                    logger.warning(
                        "Could not create vector index '%s'.",
                        index_name,
                        exc_info=True,
                    )

            # Index creation may be asynchronous. Check its actual state.
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

                return any(
                    record["type"] == "VECTOR"
                    and record["state"] == "ONLINE"
                    for record in records
                )

            except Exception:
                logger.warning(
                    "Could not verify vector index '%s'.",
                    index_name,
                    exc_info=True,
                )
                return False

    # ---------------------------------------------------------
    # DOCUMENT AND PASSAGE STORAGE
    # ---------------------------------------------------------

    def store_document_passages(
        self,
        document_name: str,
        passages: list[dict],
        *,
        document_id: str | None = None,
    ) -> None:
        """Store document passages and connect them to their document."""
        if not passages:
            return

        document_identifier = document_id or document_name

        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Document {name: $document_name})
                SET d.id = coalesce(d.id, $document_id)
                """,
                document_name=document_name,
                document_id=document_identifier,
            ).consume()

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
                    p.document_id = $document_id

                WITH p

                MATCH (d:Document {name: $document_name})

                MERGE (d)-[:HAS_PASSAGE]->(p)
                """,
                document_name=document_name,
                document_id=document_identifier,
                passages=passages,
            ).consume()

    # ---------------------------------------------------------
    # CONCEPT AND RELATIONSHIP STORAGE
    # ---------------------------------------------------------

    def store_entities_and_relationships(
        self,
        document_name: str,
        relationships: list[dict],
        *,
        document_id: str | None = None,
    ) -> None:
        """
        Store extracted concepts and their relationships.

        Each relationship should contain:
            subject, object, relation, relationship_id, passage_id

        Other properties, such as evidence, page and confidence,
        are stored when supplied.
        """
        if not relationships:
            return

        document_identifier = document_id or document_name

        concepts = sorted(
            {
                concept
                for item in relationships
                for concept in (item["subject"], item["object"])
                if concept
            }
        )

        with self.driver.session() as session:
            # Create concepts and connect them to their document.
            session.run(
                """
                MATCH (d:Document {name: $document_name})

                UNWIND $concepts AS concept_name

                MERGE (c:Concept {canonical_name: concept_name})

                SET c.aliases = coalesce(c.aliases, [])

                MERGE (d)-[:HAS_CONCEPT]->(c)
                """,
                document_name=document_name,
                concepts=concepts,
            ).consume()

            # IMPORTANT:
            # Connect passages to the concepts they mention.
            # Graph expansion and visualization depend on these edges.
            session.run(
                """
                UNWIND $relationships AS item

                MATCH (subject:Concept {
                    canonical_name: item.subject
                })

                MATCH (object:Concept {
                    canonical_name: item.object
                })

                WITH item, subject, object

                OPTIONAL MATCH (p:Passage {id: item.passage_id})

                FOREACH (_ IN CASE
                    WHEN p IS NULL THEN []
                    ELSE [1]
                END |
                    MERGE (p)-[:MENTIONS]->(subject)
                    MERGE (p)-[:MENTIONS]->(object)
                )
                """,
                relationships=relationships,
            ).consume()

            # Store the actual subject-to-object relationship.
            session.run(
                """
                UNWIND $relationships AS item

                MATCH (subject:Concept {
                    canonical_name: item.subject
                })

                MATCH (object:Concept {
                    canonical_name: item.object
                })

                MERGE (
                    subject
                )-[r:RELATES {
                    id: item.relationship_id
                }]->(
                    object
                )

                SET r.document_name = $document_name,
                    r.relation = item.relation,
                    r.evidence = item.evidence,
                    r.passageId = item.passage_id,
                    r.page = item.page,
                    r.confidence = item.confidence,
                    r.status = coalesce(item.status, 'verified'),
                    r.document_id = $document_id,
                    r.model = 'ollama'
                """,
                document_name=document_name,
                document_id=document_identifier,
                relationships=relationships,
            ).consume()

    # ---------------------------------------------------------
    # PASSAGE RETRIEVAL
    # ---------------------------------------------------------

    def search_similar_passages(
        self,
        question_vector: list[float],
        *,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Retrieve passages using the Neo4j vector index.

        If vector-index retrieval fails, calculate cosine similarity
        against stored passage embeddings instead of assigning every
        passage a misleading score of zero.
        """
        limit = (
            limit
            if limit is not None
            else self.config.vector_retrieval_count
        )

        if limit <= 0 or not question_vector:
            return []

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
                )

                return [dict(record) for record in results]

            except Exception:
                logger.warning(
                    "Vector-index retrieval failed. "
                    "Falling back to cosine similarity over stored "
                    "passage embeddings. Check the vector index.",
                    exc_info=True,
                )

            # Fallback: compare the question vector with stored vectors.
            records = session.run(
                """
                MATCH (p:Passage)
                WHERE p.embedding IS NOT NULL

                RETURN p.id AS passage_id,
                       p.text AS text,
                       p.document_name AS document_name,
                       p.page AS page,
                       p.start_offset AS start_offset,
                       p.end_offset AS end_offset,
                       p.embedding AS embedding
                """
            )

            scored_passages = []

            for record in records:
                passage = dict(record)
                passage_vector = passage.pop("embedding", None)

                if not passage_vector:
                    continue

                if len(passage_vector) != len(question_vector):
                    logger.warning(
                        "Skipping passage %s: embedding dimensions "
                        "do not match the question vector.",
                        passage.get("passage_id"),
                    )
                    continue

                dot_product = sum(
                    a * b
                    for a, b in zip(question_vector, passage_vector)
                )

                question_norm = math.sqrt(
                    sum(value * value for value in question_vector)
                )

                passage_norm = math.sqrt(
                    sum(value * value for value in passage_vector)
                )

                denominator = question_norm * passage_norm

                score = (
                    dot_product / denominator
                    if denominator > 0
                    else 0.0
                )

                passage["score"] = score
                scored_passages.append(passage)

            scored_passages.sort(
                key=lambda item: item["score"],
                reverse=True,
            )

            return scored_passages[:limit]

    # ---------------------------------------------------------
    # GRAPH EXPANSION
    # ---------------------------------------------------------

    def expand_graph(
        self,
        evidence: list[dict],
        *,
        depth: int | None = None,
    ) -> list[dict]:
        """Expand graph relationships from retrieved passages."""
        if not evidence:
            return []

        passage_ids = sorted(
            {
                item.get("passage_id")
                for item in evidence
                if item.get("passage_id")
            }
        )

        if not passage_ids:
            return []

        depth = (
            depth
            if depth is not None
            else self.config.graph_traversal_depth
        )

        if depth <= 0:
            return []

        # The fixed upper bound avoids relying on parameterized
        # variable-length relationship syntax in older Neo4j versions.
        max_depth = min(depth, 5)

        with self.driver.session() as session:
            rows = session.run(
                f"""
                MATCH (p:Passage)-[:MENTIONS]->(c:Concept)
                WHERE p.id IN $passage_ids

                MATCH path = (c)-[rels:RELATES*1..{max_depth}]-(related:Concept)

                WHERE length(rels) <= $depth

                RETURN c.canonical_name AS source,
                       related.canonical_name AS target,
                       [rel IN rels |
                           coalesce(rel.relation, type(rel))
                       ] AS relations,
                       [rel IN rels |
                           coalesce(rel.evidence, '')
                       ] AS evidence_list,
                       coalesce(p.page, 0) AS page,
                       p.id AS passage_id,
                       coalesce(p.document_name, '') AS document_name

                LIMIT 25
                """,
                passage_ids=passage_ids,
                depth=depth,
            )

            expanded = []

            for record in rows:
                item = dict(record)

                relation_names = item.pop("relations", [])
                evidence_list = item.pop("evidence_list", [])

                # Preserve the familiar single-relation fields for
                # callers that previously expected these keys.
                item["relation"] = (
                    " -> ".join(relation_names)
                    if relation_names
                    else ""
                )

                item["evidence"] = " | ".join(
                    evidence for evidence in evidence_list if evidence
                )

                expanded.append(item)

            return expanded

    # ---------------------------------------------------------
    # GRAPH DATA FOR VISUALIZATION
    # ---------------------------------------------------------

    def get_graph_data(
        self,
        document_name: str | None = None,
    ) -> dict:
        """
        Return graph nodes and edges for visualization.

        Includes Document, Passage and Concept nodes, HAS_PASSAGE,
        HAS_CONCEPT, MENTIONS and RELATES edges.
        """
        nodes: list[dict] = []
        edges: list[dict] = []

        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        def add_node(node_id: str, label: str, node_type: str) -> None:
            if node_id not in seen_nodes:
                nodes.append(
                    {
                        "id": node_id,
                        "label": label,
                        "type": node_type,
                    }
                )
                seen_nodes.add(node_id)

        def add_edge(
            source: str,
            target: str,
            label: str,
        ) -> None:
            edge_key = (source, target, label)

            if edge_key not in seen_edges:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "label": label,
                    }
                )
                seen_edges.add(edge_key)

        with self.driver.session() as session:
            # Documents and passages, including passage mentions.
            passage_rows = session.run(
                """
                MATCH (d:Document)

                WHERE $document_name IS NULL
                   OR d.name = $document_name

                OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                OPTIONAL MATCH (p)-[:MENTIONS]->(c:Concept)

                RETURN d.name AS document_name,
                       p.id AS passage_id,
                       c.canonical_name AS concept_name
                """,
                document_name=document_name,
            )

            for row in passage_rows:
                doc_name = row.get("document_name")
                passage_id = row.get("passage_id")
                concept_name = row.get("concept_name")

                if doc_name:
                    document_node_id = f"document:{doc_name}"

                    add_node(
                        document_node_id,
                        doc_name,
                        "Document",
                    )

                if passage_id:
                    passage_node_id = f"passage:{passage_id}"

                    add_node(
                        passage_node_id,
                        f"Passage {passage_id}",
                        "Passage",
                    )

                    if doc_name:
                        add_edge(
                            f"document:{doc_name}",
                            passage_node_id,
                            "HAS_PASSAGE",
                        )

                if concept_name:
                    concept_node_id = f"concept:{concept_name}"

                    add_node(
                        concept_node_id,
                        concept_name,
                        "Concept",
                    )

                    if doc_name:
                        add_edge(
                            f"document:{doc_name}",
                            concept_node_id,
                            "HAS_CONCEPT",
                        )

                    if passage_id:
                        add_edge(
                            f"passage:{passage_id}",
                            concept_node_id,
                            "MENTIONS",
                        )

            # Include concept relationships in the visualization.
            relation_rows = session.run(
                """
                MATCH (subject:Concept)-[r:RELATES]->(object:Concept)

                WHERE $document_name IS NULL
                   OR r.document_name = $document_name

                RETURN subject.canonical_name AS subject,
                       object.canonical_name AS object,
                       coalesce(r.relation, type(r)) AS relation
                """,
                document_name=document_name,
            )

            for row in relation_rows:
                subject = row.get("subject")
                object_name = row.get("object")
                relation = row.get("relation") or "RELATES"

                if not subject or not object_name:
                    continue

                subject_id = f"concept:{subject}"
                object_id = f"concept:{object_name}"

                add_node(subject_id, subject, "Concept")
                add_node(object_id, object_name, "Concept")

                add_edge(subject_id, object_id, relation)

        return {
            "nodes": nodes,
            "edges": edges,
        }

    # ---------------------------------------------------------
    # GRAPH SUMMARY
    # ---------------------------------------------------------

    def get_graph_summary(self) -> list[dict]:
        """Return passage and concept counts for each document."""
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (d:Document)

                OPTIONAL MATCH (d)-[:HAS_PASSAGE]->(p:Passage)
                OPTIONAL MATCH (d)-[:HAS_CONCEPT]->(c:Concept)
                OPTIONAL MATCH (c)-[r:RELATES]->(:Concept)

                RETURN d.name AS document_name,
                       COUNT(DISTINCT p) AS passage_count,
                       COUNT(DISTINCT c) AS concept_count,
                       COUNT(DISTINCT r) AS relationship_count

                ORDER BY document_name
                """
            )

            return [dict(record) for record in rows]