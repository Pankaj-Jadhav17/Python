from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.pdf_graph_service import PDFGraphService

router = APIRouter()
service = PDFGraphService()


class GraphIngestRequest(BaseModel):
    document_name: str
    text: str


@router.post("/ingest")
def ingest_graph(payload: GraphIngestRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    result = service.create_graph(payload.document_name, payload.text)
    return {
        "message": "Graph created from text successfully.",
        **result,
    }


@router.get("/summary")
def get_summary():
    return {"documents": service.get_graph_summary()}


@router.get("/graph")
def get_graph(document_name: str | None = None):
    return service.get_graph_data(document_name)
