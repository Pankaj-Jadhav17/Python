from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/")
async def ingest(payload: dict):
    # TODO: call ingestion service
    return {"status": "accepted", "received": payload}
