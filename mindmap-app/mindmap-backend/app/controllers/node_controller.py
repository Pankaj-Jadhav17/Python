from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("/")
async def create_node(node: dict):
    return {"id": "node-id", "node": node}


@router.get("/{node_id}")
async def get_node(node_id: str):
    return {"id": node_id, "label": "Example"}


@router.put("/{node_id}")
async def update_node(node_id: str, node: dict):
    return {"id": node_id, "updated": node}


@router.delete("/{node_id}")
async def delete_node(node_id: str):
    return {"id": node_id, "deleted": True}
