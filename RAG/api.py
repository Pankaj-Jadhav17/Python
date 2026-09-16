from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import fitz
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from .config import API_KEY
from .db import init_db
from .ingest import ingest_file, ingest_text
from .retriever import query_rag

app = FastAPI(title="RAG API")


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if not API_KEY:
        return await call_next(request)

    if request.url.path in {"/health", "/docs", "/openapi.json", "/redoc"}:
        return await call_next(request)

    provided_key = request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "")
    if provided_key != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


class IngestRequest(BaseModel):
    text: Optional[str] = None
    file_path: Optional[str] = None
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    q: str
    top_k: int = 5


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.post("/ingest")
def ingest_api(payload: IngestRequest):
    if payload.text:
        rows = ingest_text(payload.text, source=payload.source, metadata=payload.metadata)
        return {"status": "ok", "count": len(rows), "rows": rows}

    if payload.file_path:
        rows = ingest_file(payload.file_path, source=payload.source)
        return {"status": "ok", "count": len(rows), "rows": rows}

    raise HTTPException(status_code=400, detail="Provide either text or file_path")


@app.post("/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    source: str = Form("upload"),
    metadata: Optional[str] = Form(None),
):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="file is required")

    suffix = Path(file.filename).suffix.lower()
    content = await file.read()

    if suffix == ".txt":
        text = content.decode("utf-8")
    elif suffix == ".pdf":
        with fitz.open(stream=BytesIO(content), filetype="pdf") as doc:
            pages = [page.get_text("text") for page in doc]
        text = "\n\n".join(pages)
    else:
        raise HTTPException(status_code=400, detail="Only .txt and .pdf files are supported")

    final_metadata = {"file_name": file.filename}
    if metadata:
        try:
            import json
            final_metadata.update(json.loads(metadata))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata must be valid JSON")

    rows = ingest_text(text, source=source or file.filename, metadata=final_metadata)
    return {"status": "ok", "count": len(rows), "rows": rows}


@app.post("/query")
def query_api(payload: QueryRequest):
    if not payload.q.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    results = query_rag(payload.q, top_k=payload.top_k)
    return {"status": "ok", "query": payload.q, "results": results}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
