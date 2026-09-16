import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

os.environ["API_KEY"] = "test-secret"

from fastapi.testclient import TestClient

import RAG.api as rag_api
from RAG.ingest import chunk_text

rag_api.init_db = lambda: None
app = rag_api.app


def test_chunk_text_empty_string_returns_empty_list():
    assert chunk_text("") == []


def test_chunk_text_shorter_than_chunk_size_returns_original_text():
    text = "short text"
    assert chunk_text(text, chunk_size=50, overlap=10) == [text]


def test_chunk_text_overlap_is_applied_correctly():
    text = "abcdefghij"
    assert chunk_text(text, chunk_size=6, overlap=2) == ["abcdef", "efghij"]


def test_upload_route_requires_api_key_when_configured():
    client = TestClient(app)
    response = client.post(
        "/ingest/upload",
        files={"file": ("sample.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 401
