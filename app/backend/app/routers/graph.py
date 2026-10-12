from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from GraphRAG.db import GraphRAGStore

router = APIRouter()
service = GraphRAGStore()


class GraphIngestRequest(BaseModel):
    document_name: str
    text: str


@router.post("/ingest")
def ingest_graph(payload: GraphIngestRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    from GraphRAG.ingest import ingest_document_text

    result = ingest_document_text(payload.document_name, payload.text)
    return {
        "message": "Evidence graph created from text successfully.",
        **result,
    }


@router.get("/summary")
def get_summary():
    return {"documents": service.get_graph_summary()}


@router.get("/graph")
def get_graph(document_name: str | None = None):
    return service.get_graph_data(document_name)
