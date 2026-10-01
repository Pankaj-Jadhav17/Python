from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import CORS_ORIGINS
from app.routers.documents import router as documents_router
from app.routers.graph import router as graph_router

app = FastAPI(title="Document Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router, prefix="/api/documents")
app.include_router(graph_router, prefix="/api/graph")


@app.get("/")
def health_check():
    return {"status": "running"}


@app.get("/graph-view", response_class=HTMLResponse)
def graph_view():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Knowledge Graph View</title>
        <style>
            :root {
                --bg: #0f172a;
                --panel: #111827;
                --card: #1f2937;
                --text: #e5e7eb;
                --muted: #94a3b8;
                --node: #22c55e;
                --doc: #60a5fa;
                --edge: #fbbf24;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: var(--bg);
                color: var(--text);
            }
            .container {
                max-width: 1200px;
                margin: 20px auto;
                padding: 20px;
            }
            .toolbar {
                background: var(--panel);
                border: 1px solid #374151;
                border-radius: 12px;
                padding: 12px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
            }
            input {
                flex: 1;
                border: 1px solid #475569;
                background: #0b1220;
                color: var(--text);
                border-radius: 8px;
                padding: 10px 12px;
            }
            button {
                background: #2563eb;
                border: none;
                color: white;
                padding: 10px 16px;
                border-radius: 8px;
                cursor: pointer;
            }
            svg {
                width: 100%;
                min-height: 700px;
                background: linear-gradient(180deg, #111827 0%, #0b1220 100%);
                border: 1px solid #374151;
                border-radius: 12px;
            }
            .node-text {
                fill: white;
                font-size: 12px;
                text-anchor: middle;
                dominant-baseline: middle;
            }
            .edge-label {
                fill: var(--edge);
                font-size: 10px;
                text-anchor: middle;
            }
            .status {
                color: var(--muted);
                margin-top: 10px;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="toolbar">
                <input id="documentName" value="demo_graph.pdf" placeholder="Enter document name" />
                <button onclick="loadGraph()">Load Graph</button>
            </div>
            <svg id="graphSvg" viewBox="0 0 1200 700"></svg>
            <div id="status" class="status">Loading graph...</div>
        </div>

        <script>
            const svg = document.getElementById('graphSvg');
            const statusEl = document.getElementById('status');

            function drawGraph(graph) {
                const nodes = graph.nodes || [];
                const edges = graph.edges || [];

                svg.innerHTML = '';

                if (!nodes.length) {
                    statusEl.textContent = 'No graph data for this document.';
                    return;
                }

                const centerX = 600;
                const centerY = 350;
                const angleStep = (Math.PI * 2) / nodes.length;

                nodes.forEach((node, index) => {
                    const angle = angleStep * index;
                    const radius = 220;
                    const x = centerX + Math.cos(angle) * radius;
                    const y = centerY + Math.sin(angle) * radius;
                    node.x = x;
                    node.y = y;
                });

                edges.forEach((edge) => {
                    const from = nodes.find(node => node.id === edge.source);
                    const to = nodes.find(node => node.id === edge.target);
                    if (!from || !to) return;

                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', from.x);
                    line.setAttribute('y1', from.y);
                    line.setAttribute('x2', to.x);
                    line.setAttribute('y2', to.y);
                    line.setAttribute('stroke', '#fbbf24');
                    line.setAttribute('stroke-width', '2');
                    line.setAttribute('opacity', '0.75');
                    svg.appendChild(line);

                    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    label.setAttribute('x', (from.x + to.x) / 2);
                    label.setAttribute('y', (from.y + to.y) / 2 - 8);
                    label.setAttribute('class', 'edge-label');
                    label.textContent = edge.label || 'related';
                    svg.appendChild(label);
                });

                nodes.forEach((node) => {
                    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');

                    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                    const isDocument = node.type === 'Document';
                    circle.setAttribute('cx', node.x);
                    circle.setAttribute('cy', node.y);
                    circle.setAttribute('r', isDocument ? 34 : 26);
                    circle.setAttribute('fill', isDocument ? '#60a5fa' : '#22c55e');
                    circle.setAttribute('stroke', '#e5e7eb');
                    circle.setAttribute('stroke-width', '2');
                    group.appendChild(circle);

                    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    text.setAttribute('x', node.x);
                    text.setAttribute('y', node.y);
                    text.setAttribute('class', 'node-text');
                    text.textContent = node.label || node.id;
                    group.appendChild(text);

                    svg.appendChild(group);
                });

                statusEl.textContent = `Loaded ${nodes.length} nodes and ${edges.length} edges.`;
            }

            async function loadGraph() {
                const name = document.getElementById('documentName').value.trim() || 'demo_graph.pdf';
                statusEl.textContent = 'Loading graph for ' + name + '...';
                try {
                    const response = await fetch(`/api/graph/graph?document_name=${encodeURIComponent(name)}`);
                    if (!response.ok) {
                        throw new Error('Unable to load graph');
                    }
                    const graph = await response.json();
                    drawGraph(graph);
                } catch (error) {
                    statusEl.textContent = 'Error loading graph: ' + error.message;
                }
            }

            loadGraph();
        </script>
    </body>
    </html>
    """
