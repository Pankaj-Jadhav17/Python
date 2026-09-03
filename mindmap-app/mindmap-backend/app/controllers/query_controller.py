from fastapi import APIRouter

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/")
async def query(payload: dict):
    # TODO: call RAG service
    return {"answer": "not implemented", "query": payload}
