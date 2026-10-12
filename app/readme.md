# GraphRAG Knowledge Graph Application

This project is a full-stack application for turning uploaded documents into a knowledge graph and then asking natural-language questions over that graph with evidence-backed retrieval and local LLM support.

The system combines:

- a FastAPI backend
- a React + Vite frontend
- a Neo4j graph database
- Ollama for chat and embeddings
- a GraphRAG Python package for chunking, extraction, retrieval, and graph building

---

## Project purpose

The application follows a GraphRAG workflow:

1. Upload a document (PDF, DOCX, or TXT)
2. Extract and split text into chunks/passages
3. Identify concepts and relationships
4. Store the result in Neo4j as a graph
5. Ask questions in plain English
6. Retrieve the relevant graph neighborhood and produce an answer grounded in evidence

The goal is to move beyond raw document search and provide a knowledge graph that can answer structured questions using connected concepts, relationships, and supporting evidence.

---

## Main features

- File upload through a backend API
- PDF, DOCX, and TXT ingestion support
- Text extraction and chunking
- Entity and relationship extraction
- Neo4j graph persistence
- Graph summary and graph data endpoints
- Natural-language Q&A using graph evidence
- Frontend visualization of graph structure and answer paths
- Evidence display for selected relationships

---

## Technology stack

### Backend
- Python
- FastAPI
- Neo4j
- Ollama
- GraphRAG Python package

### Frontend
- React
- Vite
- TypeScript
- 3D graph visualization library

### Infrastructure
- Docker Compose
- Local Neo4j service
- Local Ollama service

---

## Project structure

```text
app/
├── docker-compose.yml
├── Dockerfile
├── readme.md
├── docs/
│   ├── README.md
│   └── pdf_neo4j_project_explanation.md
├── backend/
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirments.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── api/
│   │   ├── controllers/
│   │   ├── helpers/
│   │   ├── models/
│   │   ├── routers/
│   │   │   ├── ask.py
│   │   │   ├── documents.py
│   │   │   └── graph.py
│   │   ├── services/
│   │   │   ├── evidence_graph_service.py
│   │   │   ├── graph_question_service.py
│   │   │   └── pdf_graph_service.py
│   │   ├── utils/
│   │   └── views/
│   └── tests/
│       ├── test_graph_question_service.py
│       └── test_pdf_graph_service.py
├── GraphRAG/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── llm.py
│   ├── embeddings.py
│   ├── ingest.py
│   ├── retriever.py
│   ├── extractor.py
│   ├── graph_builder.py
│   ├── mindmap.py
│   ├── models/
│   ├── tests/
│   └── utils/
│       └── text_utils.py
└── frontend/
    ├── App.css
    ├── App.tsx
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── components/
    └── src/
        └── main.tsx
```

---

## How it works

### 1. Document ingestion
The backend accepts uploaded files and validates them before processing. The file is extracted into plain text and then split into passages or chunks. These chunks are used to identify entities, relationships, and evidence.

### 2. Graph creation
The extracted concepts and relationships are stored in Neo4j as nodes and edges. A graph can include document nodes, concept nodes, and passage nodes with relationship metadata such as:

- document name
- passage id
- page number
- relation label
- evidence quote
- confidence
- verification status

### 3. Question answering
The user asks a question using the frontend or the API. The backend matches concepts in the question to graph entities, retrieves the relevant graph neighborhood or path, then asks the LLM to answer from the graph evidence rather than from the full document blindly.

---

## API overview

### Health check
```http
GET /
```
Returns the status of the application.

### Upload document
```http
POST /api/documents/upload
```
Uploads a file and creates a graph from it.

### Get graph summary
```http
GET /api/graph/summary
```
Returns document-level graph statistics.

### Get graph JSON
```http
GET /api/graph/graph?document_name=example.pdf
```
Returns graph nodes and edges.

### Ingest raw text
```http
POST /api/graph/ingest
```
Creates graph data from a document name and raw text body.

### Ask a question
```http
POST /ask
Content-Type: application/json
```
Example request:

```json
{
  "question": "How are microspores connected to pollen grains?"
}
```

The response includes:

- `answer`: final answer text
- `path`: graph nodes and edges for the answer path
- `evidence`: relevant supporting relationship evidence

---

## Local setup

### Prerequisites

- Docker and Docker Compose
- Python 3.12+
- Node.js and npm
- Ollama installed locally

### 1. Start Neo4j
From the project root:

```bash
cd /home/pankaj/Python/app
docker compose up -d
```

Check the service:

```bash
docker compose ps
```

### 2. Start Ollama
If not already running:

```bash
ollama serve
```

Install required models:

```bash
ollama pull llama3.2:latest
ollama pull embeddinggemma:latest
```

### 3. Set up Python environment
```bash
cd /home/pankaj/Python/app
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

### 4. Start the backend
```bash
cd /home/pankaj/Python/app
. .venv/bin/activate
PYTHONPATH=/home/pankaj/Python/app/backend:/home/pankaj/Python/app python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open:

- http://localhost:8000/
- http://localhost:8000/docs

### 5. Start the frontend
```bash
cd /home/pankaj/Python/app/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Then open the app in the browser:

- http://localhost:5173

---

## Environment variables

Typical values used by the project:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_EMBEDDING_MODEL=embeddinggemma:latest
OLLAMA_TIMEOUT_SECONDS=180

GRAPHRAG_CHUNK_SIZE=1800
GRAPHRAG_CHUNK_OVERLAP=180
GRAPHRAG_VECTOR_RETRIEVAL_COUNT=8
GRAPHRAG_GRAPH_TRAVERSAL_DEPTH=2
GRAPHRAG_MAX_GRAPH_NODES=80
GRAPHRAG_MAX_GRAPH_EDGES=120
```

These settings are used by the backend and the GraphRAG package to connect to Neo4j and Ollama.

---

## Key backend files

- `backend/app/main.py` — app bootstrap and router registration
- `backend/app/routers/documents.py` — file upload support
- `backend/app/routers/graph.py` — graph querying and summaries
- `backend/app/routers/ask.py` — Q&A endpoint
- `backend/app/services/pdf_graph_service.py` — document graph creation
- `backend/app/services/evidence_graph_service.py` — evidence graph handling
- `backend/app/services/graph_question_service.py` — graph-driven answer generation

---

## Key GraphRAG files

- `GraphRAG/config.py` — config and validation
- `GraphRAG/db.py` — graph database access
- `GraphRAG/llm.py` — LLM interaction with Ollama
- `GraphRAG/embeddings.py` — embedding generation
- `GraphRAG/extractor.py` — concept and relationship extraction
- `GraphRAG/retriever.py` — retrieval for answer generation
- `GraphRAG/graph_builder.py` — graph construction logic
- `GraphRAG/utils/text_utils.py` — chunking and text utilities

---

## Example workflow

1. Run Docker and ensure Neo4j is active
2. Run Ollama and ensure the required models are installed
3. Start the backend
4. Start the frontend
5. Upload a PDF or TXT file
6. Wait for graph creation and indexing
7. Ask a question in the chat UI
8. Review the answer, graph path, and evidence details

---

## Testing

Run the targeted verification commands from the project root:

```bash
cd /home/pankaj/Python/app
. .venv/bin/activate
PYTHONPATH=/home/pankaj/Python/app/backend:/home/pankaj/Python/app pytest GraphRAG/tests/test_graph_rag_core.py backend/tests/test_graph_question_service.py -q
```

This checks the GraphRAG core functions and the existing graph question service behavior.

---

## Troubleshooting

### Neo4j connection issues
- Check that Docker Compose is running
- Confirm the database container is healthy
- Verify the credentials and URI in your environment

### Ollama issues
- Run `ollama serve`
- Verify models with `ollama list`
- Ensure the selected model names match the configuration

### Import errors
Set project path variables before running Python processes:

```bash
export PYTHONPATH=/home/pankaj/Python/app/backend:/home/pankaj/Python/app
```

### Frontend issues
- Make sure the backend is started on port 8000
- Confirm the frontend dev server is running
- Check browser console output for network errors

---

## Notes

- This project is intended for local development and prototype work.
- The quality of the graph and answers depends on the uploaded document and the local LLM model.
- The backend is designed to return structured graph data and evidence, which the frontend can display without changing the UI contract.
- The repo combines graph database capabilities with LLM-assisted retrieval to create more explainable, evidence-backed answers.

---

## Summary

This repository is a complete local GraphRAG application for building knowledge graphs from documents and asking questions over them. It is built for evidence-based explanation, graph exploration, and educational or research-oriented document understanding workflows.
