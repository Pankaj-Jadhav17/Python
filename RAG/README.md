# RAG Service Documentation

This project contains a working starter RAG (Retrieval-Augmented Generation) setup under the `RAG/` folder. It is designed to accept text or PDF input, generate embeddings, store them in PostgreSQL with `pgvector`, and then retrieve the most relevant chunks with semantic similarity search.

This README documents the actual implemented flow, the files created, the runtime workflow, and the commands you need to run.

---

## 1. What is implemented

The following functionality is already in place:

- Text chunking and overlap logic in [RAG/ingest.py](ingest.py)
- PDF/TXT extraction in [RAG/ingest.py](ingest.py)
- Embedding generation using `sentence-transformers` in [RAG/embeddings.py](embeddings.py)
- PostgreSQL insertion with pgvector in [RAG/db.py](db.py)
- Similarity search in [RAG/retriever.py](retriever.py)
- FastAPI endpoints in [RAG/api.py](api.py)
- Database schema in [RAG/db/schema.sql](db/schema.sql)
- Example usage script in [RAG/example_usage.py](example_usage.py)

### New pieces added

- `POST /ingest/upload` for PDF/TXT upload
- basic API-key middleware for security
- JSONB-safe `psycopg2` metadata handling
- chunking unit tests for edge cases

---

## 2. RAG workflow

The project flow is:

1. User passes text or a PDF/TXT file
2. The file/text is chunked into manageable pieces
3. Each chunk is converted into an embedding
4. The chunk + metadata + embedding is inserted into PostgreSQL
5. A user query is embedded and compared against stored embeddings
6. Most relevant chunks are returned as search results

This is the main logic path:

- [RAG/api.py](api.py) receives input
- [RAG/ingest.py](ingest.py) processes text/PDF
- [RAG/embeddings.py](embeddings.py) creates embeddings
- [RAG/db.py](db.py) stores vectors in PostgreSQL
- [RAG/retriever.py](retriever.py) performs similarity search

---

## 3. Files in the project

### Core files

- [RAG/api.py](api.py) — FastAPI server and endpoints
- [RAG/ingest.py](ingest.py) — ingestion + chunking logic
- [RAG/embeddings.py](embeddings.py) — embedding model wrapper
- [RAG/db.py](db.py) — DB connection + insert/search functions
- [RAG/retriever.py](retriever.py) — query embedding + retrieval logic
- [RAG/config.py](config.py) — app settings and API key config
- [RAG/example_usage.py](example_usage.py) — sample usage for text/pdf ingestion and search

### Database

- [RAG/db/schema.sql](db/schema.sql) — table definition for the vector store

### Tests

- [RAG/tests/test_ingest.py](tests/test_ingest.py) — chunk edge case validation

---

## 4. Database structure

The stored rows live in the `documents` table defined in [RAG/db/schema.sql](db/schema.sql):

```sql
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

This means:

- `content` = chunked text
- `metadata` = file name, source, or custom JSON values
- `embedding` = vector representation of the chunk

You can inspect stored data with:

```sql
SELECT id, content, metadata, created_at
FROM documents
LIMIT 10;
```

And for embeddings:

```sql
SELECT id, content, metadata, embedding
FROM documents
LIMIT 5;
```

---

## 5. Where to put your input

Because there is no frontend/backend UI yet, the input goes into Python directly or through the API.

### Direct Python usage

Use [RAG/example_usage.py](example_usage.py) and edit:

```python
text = """
Write your text or document content here.
"""
rows = ingest_text(text, source="manual", metadata={"type": "user_input"})
```

For PDF:

```python
rows = ingest_file("/absolute/path/to/file.pdf", source="pdf")
```

### API usage

Run the app:

```bash
cd /home/pankaj/GitHub_Folders/Python
python3 -m uvicorn RAG.api:app --host 0.0.0.0 --port 8000 --reload
```

Then call:

```bash
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-secret-key" \
  -d '{"text":"This is the text to embed","source":"manual"}'
```

Or upload a file:

```bash
curl -X POST "http://localhost:8000/ingest/upload" \
  -F "file=@/path/to/document.pdf" \
  -H "x-api-key: your-secret-key"
```

---

## 6. Environment setup

Create a `.env` file inside `RAG/` using [RAG/.env.example](.env.example):

```env
DATABASE_URL=postgresql://rag_user:password@localhost:5432/rag_db
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
API_HOST=0.0.0.0
API_PORT=8000
API_KEY=change-me
```

Then install dependencies:

```bash
cd /home/pankaj/GitHub_Folders/Python/RAG
python3 -m pip install -r requirements.txt
```

Ensure PostgreSQL is running and has the `pgvector` extension enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 7. Security note

The app includes a basic API-key middleware in [RAG/api.py](api.py). If `API_KEY` is set in the environment, every non-doc endpoint requires a valid key.

Example header:

```http
x-api-key: your-secret-key
```

---

## 8. What is working now

The following is implemented and runnable in principle with a PostgreSQL + pgvector database configured:

- chunking
- PDF/TXT extraction
- embedding generation
- DB insertion into pgvector
- semantic query retrieval
- FastAPI ingestion endpoints
- basic API-key protection
- file upload ingestion

### What still depends on your local environment

The remaining requirements are external to the code:

- PostgreSQL must be installed and running
- the `vector` extension must be enabled
- the `.env` file must contain the correct DB URL
- the Python packages from [RAG/requirements.txt](requirements.txt) must be installed

---

## 9. Commands to run

### Install dependencies

```bash
cd /home/pankaj/GitHub_Folders/Python/RAG
python3 -m pip install -r requirements.txt
```

### Start server

```bash
cd /home/pankaj/GitHub_Folders/Python
python3 -m uvicorn RAG.api:app --host 0.0.0.0 --port 8000 --reload
```

### Example text ingestion using script

```bash
cd /home/pankaj/GitHub_Folders/Python
python3 - <<'PY'
from RAG.ingest import ingest_text
print(ingest_text('This is sample text for embedding.'))
PY
```

### Example PDF ingestion

```bash
cd /home/pankaj/GitHub_Folders/Python
python3 - <<'PY'
from RAG.ingest import ingest_file
print(ingest_file('/path/to/file.pdf'))
PY
```

### Query stored embeddings

```bash
cd /home/pankaj/GitHub_Folders/Python
python3 - <<'PY'
from RAG.retriever import query_rag
print(query_rag('what is this document about?', top_k=5))
PY
```

---

## 10. Current status summary

This project is now a working first-stage RAG implementation for:

- text input
- PDF/TXT file ingestion
- embedding generation
- pgvector storage
- semantic retrieval

It is not a complete production UI yet, but it is executable as a backend RAG service once your database and environment are configured.

If you want next, I can add:

1. a simple `.env` file for your machine,
2. a minimal frontend form for text/PDF upload,
3. or a full backend service that saves uploaded documents and returns retrieved results in JSON.
