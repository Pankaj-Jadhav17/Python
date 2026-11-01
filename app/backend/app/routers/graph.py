from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.graph_service import service as graph_service

router = APIRouter()
service = graph_service


class CollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    collection_id: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=500)


class GraphIngestRequest(BaseModel):
    document_name: str
    text: str
    collection_id: str | None = None
    collection_name: str | None = None


@router.get("/collections")
def get_collections():
    return {"collections": service.list_collections()}


@router.post("/collections")
def create_collection(payload: CollectionCreateRequest):
    col_id = payload.collection_id or payload.name.lower().strip().replace(" ", "_")
    result = service.create_collection(
        collection_id=col_id,
        name=payload.name,
        description=payload.description,
    )
    return {
        "message": f"Collection '{payload.name}' created successfully.",
        **result,
    }


@router.post("/ingest")
def ingest_graph(payload: GraphIngestRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    from GraphRAG.ingest import ingest_document_text

    result = ingest_document_text(
        payload.document_name,
        payload.text,
        collection_id=payload.collection_id,
        collection_name=payload.collection_name,
    )
    return {
        "message": "Evidence graph created from text successfully.",
        **result,
    }


@router.get("/summary")
def get_summary():
    return {
        "documents": service.get_summary(),
        "collections": service.list_collections(),
    }


@router.get("/graph")
def get_graph(
    document_name: str | None = None,
    collection_id: str | None = None,
    community_id: int | None = None,
):
    return service.get_graph_data(
        document_name=document_name,
        collection_id=collection_id,
        community_id=community_id,
    )
