from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote

from fastapi.responses import RedirectResponse

from app.config import CORS_ORIGINS
from app.routers.ask import router as ask_router
from app.routers.documents import router as documents_router
from app.routers.graph import router as graph_router

app = FastAPI(title="Document Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router, prefix="/api/documents")
app.include_router(graph_router, prefix="/api/graph")
app.include_router(ask_router)


@app.get("/")
def health_check():
    return {"status": "running"}


@app.get("/graph-view")
def graph_view(document_name: str | None = None):
    """The old 2D SVG page was removed. Send users to the 3D React app."""
    target = CORS_ORIGINS[0].strip().rstrip("/") or "http://localhost:5173"
    if document_name:
        target += f"/?document_name={quote(document_name)}"
    return RedirectResponse(target)