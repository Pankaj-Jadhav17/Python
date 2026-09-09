# RAG Service — README

This repository contains a standalone Retrieval-Augmented Generation (RAG) service designed to be used by one or more applications. The RAG service sits under the `RAG/` folder and exposes ingestion and query functionality over HTTP (FastAPI example). The service stores documents and their vector embeddings in PostgreSQL with the `pgvector` extension.

IMPORTANT: ignore the `Python_Assignments/` folder — it is not part of this project.

## High-level structure

- `RAG/`
  - `ingestion/` — loaders and chunkers to prepare documents for embedding
  - `embeddings/` — code to compute embeddings (local models or remote API)
  - `retriever/` — retrieval logic (similarity search, top-K filtering)
  - `db/` — database schema and migration SQL
  - `api.py` — minimal FastAPI server exposing `/ingest` and `/query`
  - `requirements.txt` — Python dependencies (example)
  - `README.md` — this file

Your application lives separately under `app/` (frontend/backend). The app calls the RAG service over HTTP; it should not access the RAG DB directly unless you intentionally share the same Postgres instance.

## Recommended components & deps

- PostgreSQL (>= 14) with the `pgvector` extension
- Python 3.10+
- Libraries (sample `requirements.txt`):
  - fastapi
  - uvicorn[standard]
  - sentence-transformers
  - psycopg2-binary  # or asyncpg
  - pgvector
  - sqlalchemy (optional)
  - python-dotenv

## Database setup (quick)

1. Install Postgres and start a database server (local or managed).
2. Create a database for RAG (example `rag_db`).
3. Enable the `pgvector` extension in that DB:

```bash
psql -d rag_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

4. Apply the schema in `RAG/db/schema.sql` (or run the SQL below).

### Example SQL schema

```sql
CREATE TABLE documents (
  id SERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  metadata JSONB,
  embedding vector(1536), -- set to your embedding dim
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ivfflat index for fast similarity search (tune lists)
CREATE INDEX IF NOT EXISTS documents_embedding_idx
  ON documents USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE TABLE phase (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Example phase rows
INSERT INTO phase (name, description) VALUES
  ('ingested', 'Raw data loaded'),
  ('indexed', 'Embeddings computed and stored');
```

Notes:
- Match `embedding vector(<dim>)` to the embedding model you choose (e.g., 1536 for some OpenAI models, 384/768 for SBERT variants).
- Use `ivfflat` or `hnsw` indexes provided by `pgvector` depending on your installation; HNSW has different creation syntax.

## Environment configuration

Create a `.env` file under `RAG/` with values such as:

```env
DATABASE_URL=postgresql://rag_user:password@localhost:5432/rag_db
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
API_HOST=0.0.0.0
API_PORT=8000
```

## Example ingestion flow

1. Load source documents (PDFs, text files, URLs) with a loader in `RAG/ingestion/`.
2. Chunk long documents into smaller passages (e.g., 200–500 tokens) and add metadata (source, chunk_id).
3. Compute embeddings using `RAG/embeddings/` and store the vectors in `documents.embedding`.
4. Insert a record into `phase` or set an enum/flag to `ingested` → `indexed` as pipeline proceeds.

CLI-style example (pseudo):

```bash
python RAG/ingestion/ingest.py --source ./data --batch-size 16
```

The script should:
- read files
- produce chunks
- compute embeddings
- insert rows into `documents` with `metadata` and `embedding`
- update `phase` tracking where appropriate

## Minimal API (concept)

`RAG/api.py` should expose two endpoints at minimum:

- `POST /ingest` — accept text or file references and trigger ingestion
- `POST /query` — accept a question and `top_k`, compute embedding for the question, run a nearest-neighbors search in `documents`, and return the top results (content + metadata)

Example query request payload:

```json
{ "q": "How do I set up pgvector?", "top_k": 5 }
```

Response should include the matched `content`, `metadata`, similarity score (if desired), and optionally a `phase` filter.

## Integration with `app/`

- `app/backend` calls RAG's HTTP API to perform retrieval and provide context to LLM prompts.
- For security, the backend should authenticate requests to RAG (API keys, tokens).
- The frontend should not call the RAG DB directly.

## Local run (development)

1. Create and populate `.env` in `RAG/`.
2. Install dependencies:

```bash
cd RAG
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Ensure Postgres is running and `pgvector` is enabled.
4. Apply `RAG/db/schema.sql`.
5. Start the API server:

```bash
uvicorn RAG.api:app --host 0.0.0.0 --port 8000 --reload
```

## Security & operational notes

- Use a dedicated DB user for RAG with least privilege.
- Use TLS / private networking for DB access in production.
- Rate-limit and secure the API endpoints.
- Monitor vector index performance and tune `lists`/`probes`.

## Next steps (suggested)

1. Implement `RAG/db/schema.sql` in the repo (if not present).
2. Add `RAG/requirements.txt` or `pyproject.toml`.
3. Implement a basic `ingest.py` and `api.py` (FastAPI) — I can scaffold these for you.
4. Add tests under `RAG/tests/` for ingestion and retrieval.

If you want, I can now generate a runnable Python notebook (JSON-format) that includes:
- the `schema.sql` content, `.env` example, `requirements.txt`, and
- runnable Python cells that: connect to Postgres, create tables, perform a small ingestion using `sentence-transformers`, and run a local query via the retriever.

Reply `notebook` to create that notebook, or `scaffold` to only create minimal files (schema + README + requirements). 
