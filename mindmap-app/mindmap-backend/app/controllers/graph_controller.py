from fastapi import APIRouter

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/")
async def get_graph():
    # TODO: fetch nodes/edges from graph_model
    return {"nodes": [], "edges": []}
