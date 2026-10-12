import hashlib
import os
from pathlib import Path

from .config import config
from .db import GraphRAGStore
from .embeddings import embed_texts
from .extractor import extract_triples
from .graph_builder import build_graph_data
from .utils.text_utils import clean_text, chunk_text


def _safe_document_id(document_name: str, text: str | None = None) -> str:
    identity = f"{document_name}|{text or ''}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()[:24]


def ingest_document_text(document_name: str, text: str, *, document_id: str | None = None, store: GraphRAGStore | None = None) -> dict:
    if not isinstance(document_name, str) or not document_name.strip():
        raise ValueError("Document name is required.")
    if text is None:
        raise ValueError("Document text is required.")
    cleaned = clean_text(text)
    if not cleaned:
        raise ValueError("Document text is empty after cleaning.")
    chunks = chunk_text(cleaned, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
    if not chunks:
        raise ValueError("No chunks could be created from the provided document text.")
    vectors = embed_texts(chunks)
    if len(vectors) != len(chunks):
        raise ValueError("Embedding count does not match the number of document chunks.")

    passages = []
    for index, chunk in enumerate(chunks):
        passage_id = hashlib.sha256(f"{document_name}|{index}|{chunk}".encode("utf-8")).hexdigest()[:24]
        passages.append({
            "passage_id": passage_id,
            "document_id": document_id or _safe_document_id(document_name, cleaned),
            "document_name": document_name,
            "page": None,
            "start_offset": index * max(1, config.chunk_size - config.chunk_overlap),
            "end_offset": (index + 1) * max(1, config.chunk_size - config.chunk_overlap),
            "text": chunk,
            "embedding": vectors[index],
        })

    graph_store = store or GraphRAGStore()
    graph_store.store_document_passages(document_name, passages, document_id=document_id or _safe_document_id(document_name, cleaned))

    triples: list[dict] = []
    for index, chunk in enumerate(chunks):
        extracted = extract_triples(chunk)
        for relationship in extracted:
            triples.append({
                **relationship,
                "relationship_id": hashlib.sha256(f"{document_name}|{index}|{relationship['subject']}|{relationship['object']}|{relationship['relation']}".encode("utf-8")).hexdigest()[:24],
                "passage_id": passages[index]["passage_id"],
                "document_id": passages[index]["document_id"],
                "document_name": document_name,
                "page": None,
                "status": "verified",
            })

    if triples:
        graph_store.store_entities_and_relationships(document_name, [
            {
                "relationship_id": item["relationship_id"],
                "subject": item["subject"],
                "object": item["object"],
                "relation": item["relation"],
                "evidence": item["evidence"],
                "confidence": item["confidence"],
                "passage_id": item["passage_id"],
                "page": item["page"],
                "status": item["status"],
            }
            for item in triples
        ], document_id=document_id or _safe_document_id(document_name, cleaned))

    graph = graph_store.get_graph_data(document_name)
    return {
        "document_name": document_name,
        "document_id": document_id or _safe_document_id(document_name, cleaned),
        "passages": len(passages),
        "entities": len({item["subject"] for item in triples} | {item["object"] for item in triples}),
        "relationships": len(triples),
        "graph": graph,
    }


def ingest_file(file_path: str, *, document_name: str | None = None, store: GraphRAGStore | None = None) -> dict:
    if not file_path:
        raise ValueError("A file path is required.")
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif extension == ".pdf":
        from app.services.pdf_graph_service import PDFGraphService

        text = PDFGraphService().extract_text_from_pdf(str(path))
    elif extension == ".docx":
        from app.services.pdf_graph_service import PDFGraphService

        text = "\n".join(PDFGraphService().iter_text_chunks(str(path), extension))
    else:
        raise ValueError(f"Unsupported document type: {extension}")
    if not text or not text.strip():
        raise ValueError("No readable text was found in the uploaded document.")
    return ingest_document_text(document_name or path.name, text, store=store)
