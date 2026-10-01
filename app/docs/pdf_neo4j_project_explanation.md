# PDF to Neo4j Graph Project – Simple Explanation

## 1. What is this project about?

This project is a small learning project that shows how to take a PDF file, read the text inside it, find important words and relationships, and store them in a graph database called Neo4j.

A graph database is different from a normal table database. Instead of storing data in rows and columns, it stores data as:

- Nodes = things or objects
- Relationships = connections between them

Example:

- Node: "Machine Learning"
- Node: "Healthcare"
- Relationship: "Machine Learning helps Healthcare"

This is useful because it helps us understand how different ideas are connected.

---

## 2. Why do we need this?

In real life, documents contain lots of information. A PDF may have many paragraphs, ideas, keywords, and relationships.

If we only read the PDF as plain text, we miss the meaning behind the connections. For example:

- Machine learning is connected to healthcare.
- Deep learning is connected to cancer detection.
- AI uses RAG.

The graph helps us represent these relationships clearly.

So this project is a basic example of:

1. Read PDF
2. Extract text
3. Identify important terms
4. Detect connections
5. Store them in a graph database

---

## 3. What was built in the app?

The implementation includes:

- A FastAPI backend
- PDF upload support
- Text extraction using PyPDF
- Basic entity detection
- Relationship detection
- Neo4j graph storage
- API endpoints for upload and graph access

Important files in the project:

- [Python/app/backend/app/services/pdf_graph_service.py](../backend/app/services/pdf_graph_service.py)
- [Python/app/backend/app/routers/graph.py](../backend/app/routers/graph.py)
- [Python/app/backend/app/main.py](../backend/app/main.py)
- [Python/app/backend/README.md](../backend/README.md)
- [Python/app/readme.md](../readme.md)

---

## 4. What is FastAPI?

FastAPI is a Python framework used to build APIs quickly.

An API is a way for different systems to talk to each other.

In this project:

- The frontend or user sends a PDF to the API
- The API reads the file
- The API extracts text
- The API creates graph data
- The data is saved in Neo4j

This is a very common backend pattern in modern apps.

---

## 5. What is Neo4j?

Neo4j is a graph database.

It stores data as:

- Nodes: people, concepts, topics, entities
- Edges: relationships between them

Example:

```text
(machine learning) --helps--> (healthcare)
(deep learning) --used in--> (cancer detection)
(ai) --uses--> (rag)
```

This is much more natural for connected information than tables.

---

## 6. What is a PDF ingestion task?

"Ingestion" means bringing data into the system.

Here, we ingest a PDF by:

- accepting the file from the user
- reading the PDF content
- extracting the visible text
- processing that text
- converting it into graph data

So the PDF is not just stored; it is analyzed and converted into structured knowledge.

---

## 7. How does the project work step by step?

### Step 1: Upload PDF

The user sends a PDF file to the API endpoint:

```text
POST /api/documents/upload
```

The backend receives the file and validates that it is a PDF.

### Step 2: Read PDF content

The project uses PyPDF to open the PDF and extract text from each page.

This text is converted into a clean string.

### Step 3: Extract entities

The app looks for important terms like:

- machine learning
- deep learning
- healthcare
- cancer detection
- AI
- RAG
- Neo4j
- graph database

These are treated as entities.

### Step 4: Detect relationships

Then the system checks sentences and creates relationship patterns such as:

- machine learning helps healthcare
- deep learning used in cancer detection
- ai uses rag
- neo4j stores graph database

These are stored as graph edges.

### Step 5: Store in Neo4j

The backend uses the Neo4j driver to create nodes and relationships in the database.

The system runs queries like:

- MERGE a Document node
- MERGE Entity nodes
- CREATE relationships between them
- Link the document to the entities

### Step 6: Return graph data

The API can return data in a simple JSON format:

```json
{
  "nodes": [
    {"id": "machine learning", "label": "machine learning", "type": "Entity"},
    {"id": "healthcare", "label": "healthcare", "type": "Entity"}
  ],
  "edges": [
    {"source": "machine learning", "target": "healthcare", "label": "helps"}
  ]
}
```

This is the graph output the app is designed to show.

---

## 8. What does the service file do?

The main logic is in [Python/app/backend/app/services/pdf_graph_service.py](../backend/app/services/pdf_graph_service.py).

This file has functions like:

### extract_text_from_pdf(file_path)
This reads the PDF and returns text.

### extract_entities_and_relationships(text)
This analyzes the text and returns:

- entity list
- relationship list

### create_graph(document_name, text)
This writes the graph into Neo4j.

### get_graph_data(document_name)
This returns the graph in a structured format for use in APIs.

### get_graph_summary()
This returns document counts and relationship counts.

This is the heart of the app because it connects PDF content to graph data.

---

## 9. What does the API file do?

The route file [Python/app/backend/app/routers/graph.py](../backend/app/routers/graph.py) exposes endpoints like:

- POST /api/graph/ingest
- GET /api/graph/summary
- GET /api/graph/graph

These let the user:

- send text to build a graph
- fetch summary information
- fetch graph nodes and edges

This makes the project usable from a frontend, browser, or Postman.

---

## 10. What is the root app file doing?

The file [Python/app/backend/app/main.py](../backend/app/main.py) creates the FastAPI application.

It includes:

- app startup configuration
- CORS settings
- router registration
- a health endpoint at /

The root route returns:

```json
{"status": "running"}
```

This shows the app is online.

---

## 11. Why is this project useful for students?

This project teaches several important things:

### a) API development
You learn how backend APIs work in Python.

### b) File processing
You learn how to read and process uploaded files.

### c) NLP basics
You learn how text can be analyzed for important words and relationships.

### d) Graph thinking
You learn how information can be modeled as nodes and edges.

### e) Real-world AI application pipeline
This is a very basic version of an intelligent document processing system.

---

## 12. What is the current project status?

The project is working as a lightweight document knowledge graph system.

It does the following successfully:

- accepts PDF content
- extracts text
- detects key terms
- builds graph relationships
- exposes API endpoints
- returns graph data to the user

The only requirement for full live graph creation is that Neo4j must be running.

---

## 13. What was the actual output of the project?

The service logic was tested and it returned a result like this:

```python
(['machine learning', 'deep learning', 'data science', 'healthcare', 'cancer detection', 'ai', 'rag', 'Machine', 'learning helps healthcare', 'Deep', 'learning is used', 'in cancer detection', 'Data', 'science works with', 'uses'], [('machine learning', 'helps', 'healthcare'), ('deep learning', 'used in', 'cancer detection'), ('data science', 'works with', 'healthcare'), ('ai', 'uses', 'rag')])
```

This means:

- the system successfully found entities
- the system successfully detected relationships
- the system created graph-like knowledge from text

This is exactly the main idea of the project.

---

## 14. Why are there still some environment steps?

To fully store the graph in Neo4j, the database must be running.

The project also needed Docker/Neo4j setup in the local machine.

That is why the app root route worked, but the graph creation endpoint needed the database service to be active.

---

## 15. Simple real-world example

Imagine this PDF contains:

"Machine learning helps healthcare. Deep learning is used in cancer detection."

The project understands this as:

- Machine learning
- Healthcare
- Deep learning
- Cancer detection

And relationships:

- Machine learning helps Healthcare
- Deep learning is used in Cancer detection

Then the graph becomes:

```text
Machine learning --helps--> Healthcare
Deep learning --used in--> Cancer detection
```

This is the main idea behind knowledge graphs.

---

## 16. Summary in one paragraph

This project is a beginner-friendly example of how to build a document knowledge graph. A PDF is uploaded, its text is extracted, important topics and relationships are identified, and the data is stored in Neo4j as a graph. The backend is built with FastAPI, which provides API endpoints for upload, graph creation, and graph summary. This is a very practical project because it shows how raw unstructured documents can be transformed into structured knowledge that is easy to query and analyze.

---

## 17. How to use this as a study note

If you are a student, you can explain the project in your own words like this:

> We created a Python backend that reads PDF files, extracts text, identifies important concepts, and stores them in a Neo4j graph database. The graph shows relationships between concepts. This helps transform unstructured information into structured knowledge that can be searched and analyzed.

---

## 18. Best way to save this as PDF

This file is already written in a simple markdown format. You can open it in Visual Studio Code or a browser and then print it as a PDF.

If you want a real PDF file, open this file in a browser and use:

- Print
- Save as PDF

---

## 19. Final takeaway

This project is not just about PDF upload. It teaches a very important skill in AI and data engineering:

> turning raw text into structured knowledge.

That is exactly what knowledge graphs are for.