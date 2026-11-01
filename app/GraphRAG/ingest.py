from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.config import config
from .db import GraphRAGStore
from .document_loader import extract_document_text
from .embeddings import embed_texts
from .entity_resolution import EntityResolver
from .extractor import extract_triples
from .utils.text_utils import clean_text, chunk_text

logger = logging.getLogger(__name__)


def _safe_document_id(document_name: str, text: str | None = None, collection_id: str = "default") -> str:
    identity = f"{collection_id}|{document_name}|{text or ''}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()[:24]


def ingest_document_text(
    document_name: str,
    text: str,
    *,
    collection_id: str | None = None,
    collection_name: str | None = None,
    document_id: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """
    Ingest plain text into a collection, with duplicate detection,
    staged entity resolution, and multi-evidence graph persistence.
    """
    if not isinstance(document_name, str) or not document_name.strip():
        raise ValueError("Document name is required.")
    if text is None:
        raise ValueError("Document text is required.")

    cleaned = clean_text(text)
    if not cleaned:
        raise ValueError("Document text is empty after cleaning.")

    col_id = (collection_id or "default").strip()
    graph_store = store or GraphRAGStore()

    # Ensure collection exists
    graph_store.ensure_collection(col_id, name=collection_name)

    # 1. Duplicate Ingestion Prevention via SHA-256 Content Hash
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    existing_doc = graph_store.find_document_by_content_hash(content_hash, collection_id=col_id)
    if existing_doc:
        logger.info(
            "Document '%s' with hash %s already processed in collection '%s'. Reusing existing graph.",
            document_name,
            content_hash[:8],
            col_id,
        )
        existing_graph = graph_store.get_graph_data(collection_id=col_id)
        return {
            "document_name": document_name,
            "document_id": existing_doc.get("document_id"),
            "collection_id": col_id,
            "reused": True,
            "message": f"Document '{document_name}' has already been processed with this exact content. Reused existing graph.",
            "passages": 0,
            "entities": len(existing_graph.get("nodes", [])),
            "relationships": len(existing_graph.get("edges", [])),
            "graph": existing_graph,
        }

    # 2. Text Chunking
    chunks = chunk_text(cleaned, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
    if not chunks:
        raise ValueError("No chunks could be created from the provided document text.")

    # 3. Dense Vector Embeddings
    vectors = embed_texts(chunks)
    if len(vectors) != len(chunks):
        raise ValueError("Embedding count does not match the number of document chunks.")

    doc_id = document_id or _safe_document_id(document_name, cleaned, col_id)

    passages = []
    for index, chunk in enumerate(chunks):
        passage_id = hashlib.sha256(f"{col_id}|{document_name}|{index}|{chunk}".encode("utf-8")).hexdigest()[:24]
        chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
        passages.append({
            "passage_id": passage_id,
            "document_id": doc_id,
            "document_name": document_name,
            "collection_id": col_id,
            "chunk_index": index,
            "page": None,
            "start_offset": index * max(1, config.chunk_size - config.chunk_overlap),
            "end_offset": (index + 1) * max(1, config.chunk_size - config.chunk_overlap),
            "text": chunk,
            "content_hash": chunk_hash,
            "embedding": vectors[index],
        })

    # 4. Store Document and Passages
    graph_store.store_document_passages(
        document_name,
        passages,
        document_id=doc_id,
        collection_id=col_id,
        content_hash=content_hash,
    )

    # 5. Entity Resolution Setup
    resolver = EntityResolver(
        collection_id=col_id,
        high_confidence_threshold=getattr(config, "entity_resolution_high_threshold", 0.88),
        medium_confidence_threshold=getattr(config, "entity_resolution_medium_threshold", 0.72),
    )

    # Pre-register existing canonical entities from database
    existing_entities = graph_store.get_canonical_entities(col_id)
    for ent in existing_entities:
        resolver.register_existing_entity(
            canonical_id=ent["canonical_id"],
            canonical_name=ent["canonical_name"],
            entity_type=ent["entity_type"],
            aliases=ent["aliases"],
        )

    # 6. Extract Triples & Resolve Entities
    triples: list[dict[str, Any]] = []
    entity_map: dict[str, dict[str, Any]] = {}

    for index, chunk in enumerate(chunks):
        extracted = extract_triples(chunk, document_id=doc_id, passage_id=passages[index]["passage_id"])
        chunk_embedding = vectors[index]

        for relationship in extracted:
            subj_raw = relationship["subject"]
            obj_raw = relationship["object"]
            subj_type = relationship.get("subject_type", "Concept")
            obj_type = relationship.get("object_type", "Concept")

            subject_embedding = resolver.build_entity_embedding(subj_raw, subj_type, chunk) or chunk_embedding
            object_embedding = resolver.build_entity_embedding(obj_raw, obj_type, chunk) or chunk_embedding

            # Resolve subject
            canonical_subj = resolver.resolve_mention(
                subj_raw,
                entity_type=subj_type,
                context=chunk,
                mention_embedding=subject_embedding,
            )
            # Resolve object
            canonical_obj = resolver.resolve_mention(
                obj_raw,
                entity_type=obj_type,
                context=chunk,
                mention_embedding=object_embedding,
            )

            # Store entity details in entity_map
            entity_map[subj_raw] = {
                "canonical_id": canonical_subj.canonical_id,
                "canonical_name": canonical_subj.canonical_name,
                "entity_type": canonical_subj.entity_type,
                "aliases": canonical_subj.aliases,
            }
            entity_map[obj_raw] = {
                "canonical_id": canonical_obj.canonical_id,
                "canonical_name": canonical_obj.canonical_name,
                "entity_type": canonical_obj.entity_type,
                "aliases": canonical_obj.aliases,
            }

            rel_id = hashlib.sha256(
                f"{col_id}|{canonical_subj.canonical_id}|{relationship['relation']}|{canonical_obj.canonical_id}".encode("utf-8")
            ).hexdigest()[:24]

            triples.append({
                "subject": subj_raw,
                "subject_id": canonical_subj.canonical_id,
                "subject_canonical_name": canonical_subj.canonical_name,
                "subject_type": canonical_subj.entity_type,
                "object": obj_raw,
                "object_id": canonical_obj.canonical_id,
                "object_canonical_name": canonical_obj.canonical_name,
                "object_type": canonical_obj.entity_type,
                "relation": relationship["relation"],
                "predicate": relationship["relation"],
                "evidence": relationship["evidence"],
                "confidence": relationship["confidence"],
                "relationship_id": rel_id,
                "passage_id": passages[index]["passage_id"],
                "document_id": doc_id,
                "document_name": document_name,
                "page": relationship.get("page"),
                "status": relationship.get("status", "verified"),
            })

    # 7. Persist Resolved Concepts and Multi-Evidence Relationships
    if triples:
        graph_store.store_entities_and_relationships(
            document_name,
            triples,
            document_id=doc_id,
            collection_id=col_id,
            entity_map=entity_map,
        )

    # 8. Return Collection-Level Graph
    collection_graph = graph_store.get_graph_data(collection_id=col_id)

    return {
        "document_name": document_name,
        "document_id": doc_id,
        "collection_id": col_id,
        "reused": False,
        "passages": len(passages),
        "entities": len(entity_map),
        "relationships": len(triples),
        "graph": collection_graph,
    }


def ingest_file(
    file_path: str,
    *,
    document_name: str | None = None,
    collection_id: str | None = None,
    collection_name: str | None = None,
    store: GraphRAGStore | None = None,
) -> dict[str, Any]:
    """Ingest a file from disk into a collection."""
    if not file_path:
        raise ValueError("A file path is required.")
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif extension in {".pdf", ".docx"}:
        text = extract_document_text(str(path), extension)
    else:
        raise ValueError(f"Unsupported document type: {extension}")

    if not text or not text.strip():
        raise ValueError("No readable text was found in the uploaded document.")

    return ingest_document_text(
        document_name or path.name,
        text,
        collection_id=collection_id,
        collection_name=collection_name,
        store=store,
    )
