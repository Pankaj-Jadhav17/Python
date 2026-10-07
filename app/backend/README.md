http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000http://0.0.0.0:8000# PDF Ingestion + Neo4j Graph Backend

This backend ingests PDF, DOCX, and TXT files and uses a local Ollama model to create evidence-grounded Neo4j knowledge graphs.

## Current task status

- PDF upload support: implemented
- Text extraction and PDF page ranges: implemented with PyMuPDF
- Ollama triple extraction and evidence validation: implemented
- Low-confidence second-pass review and rejected-attempt logging: implemented
- Document, Passage, Concept, and RELATES provenance graph: implemented
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
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT_SECONDS=180
OLLAMA_CONFIDENCE_THRESHOLD=0.72
OLLAMA_NUM_PREDICT=384
```

Ollama must be running locally with the configured model installed (`ollama pull llama3.2:latest`). The upload endpoint checks that the model is available before extraction begins.

## Evidence graph

For each bounded passage, Ollama returns `subject`, `relation`, `object`, a verbatim `evidence` quote, and `confidence`. The backend rejects triples with an unsupported relation, a quote not found in the passage, or a subject/object missing from the quote. Candidates below the confidence threshold are sent to a second Ollama review and stored as `verified`, `rejected`, or `pending`.

Neo4j stores:

- `(:Document)-[:HAS_PASSAGE]->(:Passage)` with page, offsets, passage ID, and source text
- `(:Passage)-[:MENTIONS]->(:Concept)` for canonicalized concepts
- `(:Concept)-[:RELATES]->(:Concept)` with relation, evidence, passage ID, page, offsets, confidence, status, review reason, and model
- `(:Passage)-[:HAS_EXTRACTION]->(:ExtractionAttempt)` for rejected and reviewed candidate audit records

For the supplied NCERT Biology PDF, Chapter 1 is extracted from PDF pages 3–25. Use `start_page` and `end_page` query parameters on the upload endpoint to scope other PDF chapters.

## Docker for Neo4j

Use the project compose file to start Neo4j and the database services:

```powershell
cd "D:\ML_Project\Python\app"
docker compose up -d
```

## Notes

- Extraction is evidence-first but still depends on the local model's quality and the configured relation vocabulary.
- Scanned PDFs require OCR before text extraction.
