from fastapi import APIRouter

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.post("/")
async def create_relationship(rel: dict):
    return {"id": "rel-id", "relationship": rel}


@router.delete("/{rel_id}")
async def delete_relationship(rel_id: str):
    return {"id": rel_id, "deleted": True}
