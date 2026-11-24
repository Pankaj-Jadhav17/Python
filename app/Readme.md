# Graphroom — Multi-Document GraphRAG Knowledge Graph Application

Graphroom is a full-stack, enterprise-grade Knowledge Graph application powered by **GraphRAG** (Graph Retrieval-Augmented Generation). It ingests multi-format documents (PDF, DOCX, TXT, Markdown), extracts concepts and semantic relationships, organizes them into **Subject Collections**, resolves canonical entities across documents, and persists the knowledge in **Neo4j**. Users can explore graphs in an interactive **3D Force Graph** visualization and ask complex natural-language questions grounded strictly in retrieved graph evidence and original source passages using local LLMs via **Ollama** and **Graphiti-core**.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               React + Vite Frontend (3D)                               │
│  - Subject Collections Switcher & Creator      - Interactive 3D Force Graph (Three.js) │
│  - Multi-Document Upload (PDF, DOCX, TXT, MD)  - Conversational Q&A with Answer Paths  │
│  - Evidence Inspection Drawer with Citations   - Topic Community & Node Search Filters │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP / REST API
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                               FastAPI Backend Service                                  │
│  - /api/documents/upload : Multi-format document ingestion with page ranges            │
│  - /api/graph/collections: Collection management and scoping                           │
│  - /api/graph/graph      : Graph nodes and edges queryable by collection/document      │
│  - /api/graph/summary    : Global document & collection metrics                        │
│  - /ask                  : Evidence-grounded natural language Q&A                      │
└─────────────────────┬───────────────────────────────────────────┬──────────────────────┘
                      │                                           │
┌─────────────────────▼──────────────────────┐   ┌────────────────▼──────────────────────┐
│       Graphiti & Hybrid Retrieval          │   │      Graph Database & Local LLMs      │
│  - GraphitiAdapter (graphiti-core 0.31+)   │   │  - Neo4j 5.x Graph Database           │
│  - Hybrid Search with RRF (Edges, Nodes,   │   │    (Collections, Documents, Passages, │
│    Episodes, Topic Communities)            │   │     Canonical Entities, Relationships)│
│  - Cross-Encoder Reranking                 │   │  - Ollama Local LLMs:                 │
│  - Canonical Entity Resolution & Synonyms  │   │    • Chat: llama3.2                   │
│  - Strict Grounded Prompting Engine        │   │    • Embeddings: embeddinggemma       │
└────────────────────────────────────────────┘   └───────────────────────────────────────┘
```

---

## What's New in Recent Updates

### 1. Multi-Document Subject Collections
- **Organized Collections**: Documents are no longer isolated; they are grouped into dedicated Subject Collections (e.g., *Biology*, *Finance*, *Machine Learning*).
- **Collection-Scoped Operations**: Upload, graph visualization, community filtering, and Q&A can now target specific collections using normalized collection identifiers (`group_id`).
- **Dynamic Collection Management**: Create new collections directly from the frontend toolbar or API (`/api/graph/collections`).

### 2. Graphiti-Core Integration & Hybrid Search
- **Graphiti Engine**: Integrated `graphiti-core` as the primary episodic knowledge graph engine via `GraphitiAdapter`.
- **Reciprocal Rank Fusion (RRF)**: Combines four search modalities in parallel:
  1. *Graph Edges* (relationships and factual summaries)
  2. *Graph Nodes* (entities and attributes)
  3. *Episodes* (original passage texts and contexts)
  4. *Topic Communities* (hierarchical thematic summaries)
- **Cross-Encoder Reranking**: Results are reranked using local cross-encoder models for maximal semantic relevance before answer generation.
- **Dual Execution Engine**: Supports Graphiti episodic retrieval while preserving seamless fallback to direct `GraphRAGStore` Cypher execution.

### 3. Cross-Document Canonical Entity Resolution
- **Canonical Entity Linking**: Entities mentioned across different documents in the same collection automatically resolve to shared canonical nodes.
- **Multi-Stage Resolution Pipeline**:
  - Exact string normalization (NFKC, whitespace collapsing, punctuation trimming).
  - Domain synonym groups (e.g., `ATP` ↔ `Adenosine Triphosphate`, `DNA` ↔ `Deoxyribonucleic Acid`).
  - Token-level Jaccard lexical overlap.
  - Distinct identifier penalization (e.g., differentiating *RNA polymerase I* vs *II*, preventing erroneous clustering).
  - Context-aware semantic embedding similarity (`build_entity_reference_text`).
- **Provenance Preservation**: Retains multiple supporting passages and distinguishes contrasting claims without losing original source attribution.

### 4. Advanced Document Ingestion
- **Expanded File Formats**: Full native parsing for `.pdf`, `.docx`, `.txt`, and `.md` (Markdown) documents.
- **PDF Page Range Slicing**: Ingest specific page intervals using `start_page` and `end_page` parameters.
- **Idempotency & Deduplication**: SHA-256 content hashing prevents duplicate processing and tracks revisions.
- **Asynchronous Processing**: Uploads execute asynchronously via threadpools without blocking the API event loop.

### 5. Grounded Q&A with Strict Anti-Hallucination Guardrails
- **Passage-Grounded Prompting**: The retrieval pipeline extracts original passage text as primary evidence and structural graph relationships as supporting context.
- **Mandatory Source Citations**: Answers cite source document names, page numbers, and chunk indices.
- **Truthfulness Guardrails**: The LLM is instructed to report insufficient evidence if the graph lacks verified backing, preventing hallucinated answers.
- **Enriched Response Payload**: Returns `{ answer, path, evidence, nodes, communities }`.

### 6. Interactive 3D Knowledge Graph UI
- **3D Force Graph Engine**: Implemented using `3d-force-graph` and Three.js with 60 FPS rendering.
- **Interactive Camera**: Clicking any node triggers a smooth 3D camera fly-to animation.
- **Entity Type & Community Palette**: Dynamic color coding based on semantic entity types (*BiologicalEntity*, *ChemicalEntity*, *Process*, *Organization*, *Person*, *Location*, etc.) or community clusters.
- **Answer Path Visualization**: Animated directional particles trace the exact reasoning path used to answer a question.
- **Quick-Prompt Generation**: Clicking a node allows one-click question asking: *"Explain concept [X] in the context of collection [Y]"*.
- **Large Graph Optimization**: Automatic degree-based pruning keeps rendering fast and fluid even on dense graphs (>240 nodes).

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.12+, FastAPI, Uvicorn, Pydantic v2, Starlette |
| **GraphRAG Engine** | `graphiti-core` 0.31+, LangChain, PyMuPDF (fitz), python-docx |
| **Graph Database** | Neo4j 5.x (Cypher, APOC, Bolt Protocol) |
| **LLM & Embeddings** | Ollama (`llama3.2` for chat/reasoning, `embeddinggemma` for vector embeddings) |
| **Frontend** | React 18, TypeScript, Vite, `3d-force-graph`, Three.js, CSS3 Custom Properties |
| **Testing** | Pytest, AnyIO, AsyncMock (40 automated tests) |

---

## Project Structure

```text
app/
├── docker-compose.yml              # Local services (Neo4j, Ollama)
├── Dockerfile                      # Backend container configuration
├── pytest.ini                      # Pytest configuration
├── readme.md                       # Main project documentation
├── Document.txt                    # Detailed system documentation
├── Documentation.txt               # In-depth architectural & API documentation
├── docs/                           # Extended documentation and guides
│   ├── README.md
│   └── pdf_neo4j_project_explanation.md
├── backend/                        # FastAPI application
│   ├── pyproject.toml              # Dependencies & package metadata
│   ├── requirements.txt            # Python dependencies
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py               # Environment configuration and validation
│   │   ├── main.py                 # FastAPI application & lifespan management
│   │   ├── routers/
│   │   │   ├── ask.py              # POST /ask endpoint
│   │   │   ├── documents.py        # POST /api/documents/upload endpoint
│   │   │   └── graph.py            # Collections, summaries, and graph query endpoints
│   │   └── services/
│   │       ├── document_service.py # Ingestion & Ollama validation service
│   │       ├── graph_service.py    # Graph metadata & collection query service
│   │       └── question_service.py # Asynchronous retrieval & answering service
│   └── tests/                      # Backend test suite
│       ├── test_collection_graphrag.py      # Multi-document & collection tests
│       ├── test_graph_question_service.py   # Q&A service verification
│       ├── test_graphiti_integration.py     # Graphiti adapter tests
│       ├── test_graphiti_rag_retrieval.py   # Hybrid search & retrieval tests
│       └── test_pdf_graph_service.py        # Loader & extractor unit tests
├── GraphRAG/                       # Core GraphRAG package
│   ├── __init__.py
│   ├── db.py                       # Direct Neo4j store implementation
│   ├── document_loader.py          # PDF, DOCX, TXT loaders & page-range splitters
│   ├── embeddings.py               # Ollama vector embedding generation
│   ├── entity_resolution.py        # Canonical entity resolution & synonym linking
│   ├── extractor.py                # LLM relationship & concept extraction
│   ├── graph_builder.py            # Graph construction routines
│   ├── graphiti_integration.py     # GraphitiAdapter & RRF hybrid search pipeline
│   ├── ingest.py                   # Unified document ingestion pipeline
│   ├── llm.py                      # Ollama client and model verification
│   ├── mindmap.py                  # Mindmap utilities
│   ├── models/
│   │   └── graph_models.py         # Dataclasses (CanonicalEntity, Mentions, Passages)
│   ├── tests/
│   │   ├── evaluation_dataset.py   # Evaluation fixtures
│   │   ├── test_evaluation_metrics.py
│   │   └── test_graph_rag_core.py
│   └── utils/
│       └── text_utils.py           # Text cleaning and overlapping chunking
└── frontend/                       # React + Vite 3D application
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── App.css                     # Responsive styles and color themes
    ├── App.tsx                     # Main 3D Graphroom UI & Q&A interface
    └── src/
        └── main.tsx                # React entry point
```

---

## API Endpoints Reference

### 1. Health & Navigation
- `GET /` — Returns `{"status": "running"}`.
- `GET /graph-view?document_name=...` — Redirects browser to the 3D React graph view.

### 2. Document Ingestion
- `POST /api/documents/upload`
  - **Content-Type**: `multipart/form-data`
  - **Form Fields**:
    - `file`: File upload (`.pdf`, `.docx`, `.txt`, `.md`).
    - `collection_id` *(optional)*: Target subject collection (e.g. `biology`).
    - `collection_name` *(optional)*: Human-readable collection name.
    - `start_page` *(optional, PDF only)*: Starting page number (1-based).
    - `end_page` *(optional, PDF only)*: Ending page number (1-based).
  - **Response**: Ingestion result including passages created, entities extracted, relationships formed, and content reuse status.

### 3. Collection Management
- `GET /api/graph/collections`
  - Returns list of existing collections with IDs, names, and descriptions.
- `POST /api/graph/collections`
  - **JSON Body**: `{"name": "Neuroscience", "collection_id": "neuro", "description": "Brain studies"}`
  - Creates a new collection node in Neo4j.

### 4. Graph Queries & Summaries
- `GET /api/graph/summary`
  - Returns document summary lists (document name, hash, revision) and collection metadata.
- `GET /api/graph/graph`
  - **Query Parameters**:
    - `collection_id`: Filter by collection (e.g. `default`, `biology`).
    - `document_name`: Filter by specific document.
    - `community_id`: Filter by detected community group.
  - **Response**: Graph payload with `{ nodes: [...], edges: [...] }`.
- `POST /api/graph/ingest`
  - Ingest raw text directly with `{"document_name": "note.txt", "text": "...", "collection_id": "..."}`.

### 5. Grounded Question Answering
- `POST /ask`
  - **JSON Body**:
    ```json
    {
      "question": "What is the function of microspores in plant reproduction?",
      "collection_id": "biology"
    }
    ```
  - **Response Payload**:
    ```json
    {
      "answer": "Microspores develop into pollen grains which represent the male gametophyte generation (Source: botany.pdf, Page 12)...",
      "path": {
        "nodes": [{"id": "microspore", "label": "Microspore", "type": "BiologicalEntity"}],
        "edges": [{"source": "microspore", "target": "pollen_grain", "label": "develops_into"}]
      },
      "evidence": [
        {
          "document_name": "botany.pdf",
          "page": 12,
          "chunk_index": 2,
          "text": "Each microspore mother cell undergoes meiosis to form four haploid microspores...",
          "confidence": 0.95
        }
      ],
      "nodes": [...],
      "communities": [...]
    }
    ```

---

## Environment Configuration

Configure the application by creating or editing `.env` in the root directory:

```env
# Neo4j Graph Database
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password

# Ollama Local LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=embeddinggemma
OLLAMA_TIMEOUT_SECONDS=180
OLLAMA_CONFIDENCE_THRESHOLD=0.72
OLLAMA_NUM_PREDICT=384

# GraphRAG Hyperparameters
GRAPHRAG_CHUNK_SIZE=1800
GRAPHRAG_CHUNK_OVERLAP=180
GRAPHRAG_VECTOR_RETRIEVAL_COUNT=8
GRAPHRAG_GRAPH_TRAVERSAL_DEPTH=2
GRAPHRAG_MAX_GRAPH_NODES=80
GRAPHRAG_MAX_GRAPH_EDGES=120

# Entity Resolution Thresholds
ENTITY_RESOLUTION_HIGH_THRESHOLD=0.88
ENTITY_RESOLUTION_MEDIUM_THRESHOLD=0.72

# CORS Configuration
CORS_ORIGINS=http://localhost:5173
```

---

## Local Setup & Quick Start

### 1. Prerequisites
- **Python 3.12+**
- **Node.js 18+** & npm
- **Docker & Docker Compose** (for Neo4j)
- **Ollama** installed locally

### 2. Start Infrastructure
Start the Neo4j container:
```bash
docker compose up -d
```

Verify Ollama is running and download required models:
```bash
ollama serve &
ollama pull llama3.2
ollama pull embeddinggemma
```

### 3. Backend Setup
Activate the virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Launch the FastAPI backend server:
```bash
PYTHONPATH=backend:. python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/](http://localhost:8000/)

### 4. Frontend Setup
In a new terminal:
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```
Open your browser at [http://localhost:5173](http://localhost:5173).

---

## Running Automated Tests

Run the complete test suite (40 tests covering ingestion, resolution, hybrid search, and Graphiti integration):

```bash
source .venv/bin/activate
PYTHONPATH=backend:. pytest backend/tests/ GraphRAG/tests/ -v
```

All 40 unit and integration tests validate:
- Multi-document canonical entity deduplication and synonym resolution.
- Contrastive numeral differentiation (e.g. *Polymerase I* vs *II*).
- Graphiti hybrid search activation across nodes, edges, episodes, and communities.
- Grounded prompt construction and source document provenance.
- Document loader chunking and PDF page-range extraction.
