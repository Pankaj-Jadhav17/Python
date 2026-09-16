from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json
from pgvector.psycopg2 import register_vector

from .config import DATABASE_URL, SCHEMA_PATH


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def init_db() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    sql = SCHEMA_PATH.read_text()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def insert_document(content: str, metadata: Optional[Dict[str, Any]], embedding: List[float]) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (content, metadata, embedding) VALUES (%s, %s, %s) RETURNING id",
                (content, Json(metadata or {}), embedding),
            )
            document_id = cur.fetchone()[0]
        conn.commit()
        return document_id
    finally:
        conn.close()


def insert_documents(documents: List[Dict[str, Any]]) -> None:
    if not documents:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO documents (content, metadata, embedding) VALUES (%s, %s, %s)",
                [
                    (
                        item["content"],
                        Json(item.get("metadata") or {}),
                        item["embedding"],
                    )
                    for item in documents
                ],
            )
        conn.commit()
    finally:
        conn.close()


def search_documents(query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content, metadata, 1 - (embedding <=> %s) AS score
                FROM documents
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": row[2],
                "score": float(row[3]),
            }
            for row in rows
        ]
    finally:
        conn.close()
