http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000# PDF Ingestion + Neo4j Graph Backend

This backend ingests PDF files, extracts key entities and relationships, and creates a Neo4j knowledge graph from the document content.

## Current task status

- PDF upload support: implemented
- Text extraction: implemented
- Entity and relationship detection: implemented
- Neo4j graph generation: implemented
- Graph summary endpoint: implemented
- Swagger UI: available at `/docs`
- Visual graph page: available at `/graph-view`

## Task description

This project implements the PDF ingestion + Neo4j graph task. The backend reads a PDF, extracts text, detects entities and relationships, creates graph nodes and edges in Neo4j, and exposes the result through API endpoints.

## Run locally

```powershell
cd "D:\ML_Project\Python\app\backend"
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:

- http://localhost:8000/
- http://localhost:8000/docs
- http://localhost:8003/graph-view

> The graph UI route is served on port 8003 in the current setup because port 8002 is already occupied on this machine.

## API endpoints

- `GET /` → health check
- `POST /api/documents/upload` → upload PDF and create graph
- `POST /api/graph/ingest` → create graph from raw text
- `GET /api/graph/summary` → graph statistics
- `GET /api/graph/graph` → graph nodes and edges payload

## Example output

The API returns graph data in this format:

```json
{
  "nodes": [
    {"id": "machine learning", "label": "machine learning", "type": "Entity"},
    {"id": "healthcare", "label": "healthcare", "type": "Entity"},
    {"id": "deep learning", "label": "deep learning", "type": "Entity"},
    {"id": "cancer detection", "label": "cancer detection", "type": "Entity"}
  ],
  "edges": [
    {"source": "machine learning", "target": "healthcare", "label": "helps"},
    {"source": "deep learning", "target": "cancer detection", "label": "used in"}
  ]
}
```

To test the graph endpoint directly:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8002/api/graph/graph?document_name=demo_graph.pdf'
```

## Environment

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
CORS_ORIGINS=http://localhost:5173
```

## Docker for Neo4j

Use the project compose file to start Neo4j and the database services:

```powershell
cd "D:\ML_Project\Python\app"
docker compose up -d
```

## Notes

- The current implementation is a working lightweight knowledge graph builder based on document text.
- It is suitable for demo and learning projects, and can be extended with an LLM extractor or richer entity recognition later.
