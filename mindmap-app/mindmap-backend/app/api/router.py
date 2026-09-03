from fastapi import APIRouter
from app.controllers import (ingest_controller, query_controller,node_controller,
    relationship_controller,
    graph_controller,
)

router = APIRouter()

router.include_router(ingest_controller.router)
router.include_router(query_controller.router)
router.include_router(node_controller.router)
router.include_router(relationship_controller.router)
router.include_router(graph_controller.router)
