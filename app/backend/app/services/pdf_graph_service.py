import os
import re
from typing import Iterable

from neo4j import GraphDatabase
from pypdf import PdfReader, apply_configuration

from app.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


class PDFGraphService:
    """Extract text from PDF files and create a Neo4j knowledge graph."""

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self.uri = uri or NEO4J_URI or "bolt://localhost:7687"
        self.user = user or NEO4J_USER or "neo4j"
        self.password = password or NEO4J_PASSWORD or "your_neo4j_password"
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def extract_text_from_pdf(self, file_path: str) -> str:
        pages = []
        with apply_configuration(zlib_maximum_output_length=250_000_000):
            reader = PdfReader(file_path)
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
        return "\n".join(pages).strip()

    def extract_entities_and_relationships(self, text: str):
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return [], []

        entities = []
        relationships = []

        known_terms = [
            "machine learning",
            "deep learning",
            "data science",
            "healthcare",
            "cancer detection",
            "neural networks",
            "natural language processing",
            "ai",
            "rag",
            "neo4j",
            "graph database",
            "pdf",
        ]
        lowered_text = normalized.lower()
        for term in known_terms:
            if term in lowered_text and term not in entities:
                entities.append(term)

        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if "machine learning" in sentence_lower and "healthcare" in sentence_lower:
                relationships.append(("machine learning", "helps", "healthcare"))
            if "deep learning" in sentence_lower and "cancer detection" in sentence_lower:
                relationships.append(("deep learning", "used in", "cancer detection"))
            if "data science" in sentence_lower and "healthcare" in sentence_lower:
                relationships.append(("data science", "works with", "healthcare"))
            if "ai" in sentence_lower and "rag" in sentence_lower:
                relationships.append(("ai", "uses", "rag"))
            if "neo4j" in sentence_lower and "graph database" in sentence_lower:
                relationships.append(("neo4j", "stores", "graph database"))

        extra_entities = re.findall(
            r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[a-z]+(?:\s+[a-z]+){0,2})\b",
            normalized,
        )
        for candidate in extra_entities:
            cleaned = re.sub(r"\s+", " ", candidate).strip()
            if len(cleaned) < 3:
                continue
            if cleaned.lower() in {"the", "and", "for", "with", "that", "this"}:
                continue
            if cleaned.lower() not in {entity.lower() for entity in entities}:
                entities.append(cleaned)

        unique_entities = []
        seen = set()
        for entity in entities:
            key = entity.lower().strip()
            if key not in seen:
                unique_entities.append(entity.strip())
                seen.add(key)

        unique_relationships = []
        seen_relationships = set()
        for source, rel_type, target in relationships:
            key = (source.lower(), rel_type.lower(), target.lower())
            if key not in seen_relationships:
                unique_relationships.append((source, rel_type, target))
                seen_relationships.add(key)

        return unique_entities, unique_relationships

    def create_graph(self, document_name: str, text: str):
        entities, relationships = self.extract_entities_and_relationships(text)

        with self.driver.session() as session:
            session.run(
                "MERGE (d:Document {name: $document_name})",
                document_name=document_name,
            )

            for entity in entities:
                session.run(
                    "MERGE (:Entity {name: $name})",
                    name=entity,
                )

            for source, relation_type, target in relationships:
                session.run(
                    """
                    MATCH (source:Entity {name: $source})
                    MATCH (target:Entity {name: $target})
                    MERGE (source)-[r:RELATED_TO {type: $relation_type}]->(target)
                    """,
                    source=source,
                    relation_type=relation_type,
                    target=target,
                )

            for entity in entities:
                session.run(
                    """
                    MATCH (doc:Document {name: $document_name})
                    MATCH (entity:Entity {name: $entity})
                    MERGE (doc)-[:CONTAINS]->(entity)
                    """,
                    document_name=document_name,
                    entity=entity,
                )

        graph_data = self.get_graph_data(document_name)

        return {
            "document_name": document_name,
            "entities": len(entities),
            "relationships": len(relationships),
            "graph": graph_data,
        }

    def get_graph_data(self, document_name: str | None = None):
        with self.driver.session() as session:
            query = """
                MATCH (d:Document)-[contains:CONTAINS]->(e:Entity)
                WHERE $document_name IS NULL OR d.name = $document_name
                OPTIONAL MATCH (e)-[r]->(other:Entity)
                RETURN d.name AS document_name, e.name AS entity_name,
                       type(contains) AS document_relationship,
                       type(r) AS relationship_type, other.name AS related_entity
                """
            result = session.run(query, document_name=document_name)
            rows = [dict(record) for record in result]

        nodes = []
        edges = []
        seen_nodes = set()

        for row in rows:
            doc_name = row.get("document_name")
            entity_name = row.get("entity_name")
            related_entity = row.get("related_entity")
            relationship_type = row.get("relationship_type")
            document_relationship = row.get("document_relationship")

            if entity_name and entity_name not in seen_nodes:
                nodes.append({"id": entity_name, "label": entity_name, "type": "Entity"})
                seen_nodes.add(entity_name)
            if related_entity and related_entity not in seen_nodes:
                nodes.append({"id": related_entity, "label": related_entity, "type": "Entity"})
                seen_nodes.add(related_entity)
            if doc_name and doc_name not in seen_nodes:
                nodes.append({"id": doc_name, "label": doc_name, "type": "Document"})
                seen_nodes.add(doc_name)
            if doc_name and entity_name and document_relationship:
                edges.append({
                    "source": doc_name,
                    "target": entity_name,
                    "label": document_relationship,
                })
            if entity_name and related_entity and relationship_type:
                edges.append({
                    "source": entity_name,
                    "target": related_entity,
                    "label": relationship_type,
                })

        return {"nodes": nodes, "edges": edges}

    def get_graph_summary(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)-[:CONTAINS]->(e:Entity)
                OPTIONAL MATCH (e)-[r]->(other:Entity)
                RETURN d.name AS document_name, count(DISTINCT e) AS entity_count, count(DISTINCT r) AS relationship_count
                """
            )
            rows = [dict(record) for record in result]
        return rows

    def close(self):
        self.driver.close()
