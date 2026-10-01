# Project Overview

This repository contains a full-stack application with a Python backend, a frontend, and Docker-based services. The backend also implements PDF ingestion and Neo4j knowledge-graph generation.

## PDF-to-Neo4j task

The backend accepts a PDF, extracts its text with PyPDF, identifies entities and selected relationships, and stores the resulting document graph in Neo4j. Graph data is available through API endpoints and a browser-based graph view.

Task flow:

1. Upload a PDF through the API.
2. Extract text from the PDF.
3. Detect entities and relationships.
4. Store document and entity nodes and their edges in Neo4j.
5. Retrieve the graph as JSON or view it on the graph page.

The entity and relationship extraction is a lightweight demo implementation, not a general-purpose semantic extraction model.

## Quick start

### 1. Start Neo4j

Make sure Docker Desktop is running, then start Neo4j from the app folder:

```powershell
cd "D:\ML_Project\Python\app"
docker compose up -d --wait neo4j
docker compose ps neo4j
```

Neo4j Browser is available at `http://localhost:7474`. The Compose defaults are username `neo4j` and password `your_neo4j_password`; change these for non-local use.

### 2. Start the backend

In a separate PowerShell terminal:

```powershell
cd "D:\ML_Project\Python\app\backend"
$env:PYTHONPATH = "$PWD"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If port 8000 is already in use, choose another port, such as 8003, and use that same port in the URLs below.

### 3. Open the app

- Swagger API docs: `http://localhost:8000/docs`
- Visual graph page: `http://localhost:8000/graph-view`
- API health check: `http://localhost:8000/`
- Neo4j Browser: `http://localhost:7474`

Use `localhost` in the browser. `0.0.0.0` is the server bind address, not the browser URL.

### 4. Upload a PDF and view its graph

In Swagger, open `POST /api/documents/upload`, choose a PDF, and execute the request. Then open the graph page and enter the uploaded PDF's exact filename. The page requests the graph from the backend and draws its nodes and edges.

To inspect JSON directly, use this PowerShell command, replacing the filename if needed:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/api/graph/graph?document_name=demo_graph.pdf' | ConvertTo-Json -Depth 20
```

## API endpoints

- `POST /api/documents/upload` uploads a PDF, extracts its text, and creates its graph.
- `POST /api/graph/ingest` creates a graph from a document name and raw text.
- `GET /api/graph/graph` returns graph nodes and edges. The optional `document_name` query filters by document.
- `GET /api/graph/summary` returns graph counts by document.

Example text-ingestion request:

```powershell
$body = @{
   document_name = 'demo_graph.pdf'
   text = 'Machine learning helps healthcare. Deep learning is used in cancer detection.'
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
   -Uri 'http://localhost:8000/api/graph/ingest' `
   -ContentType 'application/json' `
   -Body $body
```

The graph response contains `nodes` (documents and entities) and `edges` (their relationships).

## Project structure

```text
app/
├── backend/       Python API, graph service, and tests
├── frontend/      React frontend
├── docs/          Project documentation
├── docker-compose.yml
├── Dockerfile
└── readme.md
```

## Tests

From `app/backend`, run the focused graph-service test with:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_pdf_graph_service.py -q
```

## Notes

- Neo4j must be running before uploading or ingesting graph data.
- Keep local credentials in environment configuration and use secure credentials outside development.
- The API root returns `{"status": "running"}` as a health check; graph data is available from the graph endpoints or visual graph page.
