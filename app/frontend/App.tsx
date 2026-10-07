import { FormEvent, useEffect, useMemo, useState } from 'react';
import './App.css';

type GraphNode = { id: string; label: string; type: 'Document' | 'Concept' | 'Passage'; page?: number };
type GraphEdge = {
  source: string;
  target: string;
  label: string;
  evidence?: string;
  passageId?: string;
  page?: number;
  confidence?: number;
  status?: 'verified' | 'pending' | 'rejected';
  verificationReason?: string;
};
type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const MAX_VISIBLE_NODES = 180;

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [startPage, setStartPage] = useState('');
  const [endPage, setEndPage] = useState('');
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [documentName, setDocumentName] = useState('');
  const [status, setStatus] = useState('Choose a PDF, DOCX, or TXT file to begin.');
  const [isUploading, setIsUploading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  useEffect(() => {
    const requestedDocument = new URLSearchParams(window.location.search).get('document_name');
    if (!requestedDocument) return;

    let cancelled = false;
    setDocumentName(requestedDocument);
    setStatus(`Loading ${requestedDocument} from Neo4j...`);
    fetch(`${API_BASE_URL}/api/graph/graph?document_name=${encodeURIComponent(requestedDocument)}`)
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail ?? 'Could not load this graph.');
        return result as GraphData;
      })
      .then((result) => {
        if (cancelled) return;
        setGraph(result);
        setStatus(`Loaded ${result.nodes.length} nodes and ${result.edges.length} connections from Neo4j.`);
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatus(error instanceof Error ? error.message : 'Could not load this graph.');
      });

    return () => { cancelled = true; };
  }, []);

  const visibleGraph = useMemo(() => {
    if (!graph) return null;
    const nodes = graph.nodes.slice(0, MAX_VISIBLE_NODES);
    const visibleIds = new Set(nodes.map((node) => node.id));
    return {
      nodes,
      edges: graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
    };
  }, [graph]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    const pageRange = new URLSearchParams();
    if (startPage) pageRange.set('start_page', startPage);
    if (endPage) pageRange.set('end_page', endPage);
    const pageQuery = pageRange.toString();
    setIsUploading(true);
    setStatus(`Uploading and processing ${file.name}...`);
    setSelectedNode(null);
    setSelectedEdge(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/upload${pageQuery ? `?${pageQuery}` : ''}`, {
        method: 'POST',
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail ?? 'The document could not be processed.');
      }

      setGraph(result.graph);
      setDocumentName(result.document_name);
      setStatus(
        `${result.passages} passages · ${result.entities} concepts · ${result.verified} verified · ` +
        `${result.pending} pending · ${result.rejected} rejected`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'The document could not be processed.');
    } finally {
      setIsUploading(false);
    }
  }

  const nodes = visibleGraph?.nodes ?? [];
  const positions = new Map(
    nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / Math.max(nodes.length, 1) - Math.PI / 2;
      const radius = node.type === 'Document' ? 0 : 230;
      return [node.id, { x: 500 + Math.cos(angle) * radius, y: 310 + Math.sin(angle) * radius }];
    }),
  );

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Graphroom home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>Graphroom</span>
        </a>
        <span className="connection"><span className="connection-dot" /> NEO4J WORKSPACE</span>
      </header>

      <section className="intro" id="top">
        <div>
          <p className="eyebrow">DOCUMENT KNOWLEDGE GRAPH</p>
          <h1>Turn a document<br />into connected ideas.</h1>
        </div>
        <p className="intro-copy">Upload a file to extract concepts, map their relationships, and explore the graph stored in Neo4j.</p>
      </section>

      <section className="ingest" aria-label="Document upload">
        <form className="upload-form" onSubmit={handleUpload}>
          <label className={`file-picker ${file ? 'has-file' : ''}`}>
            <input
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              onChange={(event) => {
                const selectedFile = event.target.files?.[0] ?? null;
                setFile(selectedFile);
                if (!selectedFile?.name.toLowerCase().endsWith('.pdf')) {
                  setStartPage('');
                  setEndPage('');
                }
              }}
            />
            <span className="upload-glyph" aria-hidden="true">↑</span>
            <span className="file-copy">
              <strong>{file?.name ?? 'Choose a document'}</strong>
              <small>{file ? `${(file.size / (1024 * 1024)).toFixed(2)} MB · Ready to process` : 'PDF, DOCX, or TXT'}</small>
            </span>
            <span className="browse-label">Browse</span>
          </label>
          <button className="process-button" type="submit" disabled={!file || isUploading}>
            {isUploading ? <span className="spinner" /> : <span aria-hidden="true">↗</span>}
            {isUploading ? 'Processing' : 'Build graph'}
          </button>
        </form>
        {file?.name.toLowerCase().endsWith('.pdf') && (
          <div className="page-range">
            <label>From page<input aria-label="Start PDF page" type="number" min="1" value={startPage} onChange={(event) => setStartPage(event.target.value)} placeholder="1" /></label>
            <span>to</span>
            <label>Through page<input aria-label="End PDF page" type="number" min="1" value={endPage} onChange={(event) => setEndPage(event.target.value)} placeholder="all" /></label>
            <span className="page-range-note">Optional PDF page range</span>
          </div>
        )}
        <p className={`status ${status.includes('stored') ? 'success' : ''}`} role="status">{status}</p>
      </section>

      <section className="graph-section" aria-label="Generated graph">
        <div className="graph-heading">
          <div>
            <p className="eyebrow">EXPLORER</p>
            <h2>{documentName || 'Your graph'}</h2>
          </div>
          {graph && (
            <div className="graph-stats">
              <span><b>{graph.nodes.length}</b> nodes</span>
              <span><b>{graph.edges.length}</b> connections</span>
            </div>
          )}
        </div>

        <div className={`graph-canvas ${graph ? 'populated' : ''}`}>
          {visibleGraph && visibleGraph.nodes.length > 0 ? (
            <svg viewBox="0 0 1000 620" role="img" aria-label="Document knowledge graph">
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill="#9baba5" />
                </marker>
              </defs>
              {visibleGraph.edges.map((edge, index) => {
                const source = positions.get(edge.source);
                const target = positions.get(edge.target);
                if (!source || !target) return null;
                return (
                  <g
                    key={`${edge.source}-${edge.target}-${index}`}
                    className={`edge ${edge.evidence ? 'evidence-edge' : ''} ${selectedEdge === edge ? 'selected' : ''}`}
                    role={edge.evidence ? 'button' : undefined}
                    tabIndex={edge.evidence ? 0 : undefined}
                    aria-label={edge.evidence ? `${edge.label}: ${edge.evidence}` : undefined}
                    onClick={edge.evidence ? () => setSelectedEdge(edge) : undefined}
                    onKeyDown={edge.evidence ? (event) => {
                      if (event.key === 'Enter' || event.key === ' ') setSelectedEdge(edge);
                    } : undefined}
                  >
                    {edge.evidence && <title>{edge.evidence}</title>}
                    <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} markerEnd="url(#arrow)" />
                    <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 7}>{edge.label}</text>
                  </g>
                );
              })}
              {visibleGraph.nodes.map((node) => {
                const point = positions.get(node.id);
                if (!point) return null;
                const isDocument = node.type === 'Document';
                const isPassage = node.type === 'Passage';
                const label = node.label.length > 16 ? `${node.label.slice(0, 14)}…` : node.label;
                return (
                  <g
                    key={node.id}
                    className={`node ${isDocument ? 'document-node' : ''} ${isPassage ? 'passage-node' : ''} ${selectedNode?.id === node.id ? 'selected' : ''}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${node.type}: ${node.label}`}
                    onClick={() => setSelectedNode(node)}
                    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedNode(node); }}
                  >
                    <title>{node.label} · {node.type}</title>
                    <circle cx={point.x} cy={point.y} r={isDocument ? 39 : isPassage ? 20 : 27} />
                    <text x={point.x} y={point.y + 48}>{label}</text>
                  </g>
                );
              })}
            </svg>
          ) : (
            <div className="empty-graph">
              <div className="empty-mark" aria-hidden="true"><span /><span /><span /><span /></div>
              <strong>The graph will appear here</strong>
              <span>Upload a document to see its entities and connections.</span>
            </div>
          )}
          {graph && graph.nodes.length > MAX_VISIBLE_NODES && (
            <p className="graph-limit">Showing {MAX_VISIBLE_NODES} of {graph.nodes.length} nodes for a responsive view.</p>
          )}
        </div>
        {selectedNode && !selectedEdge && (
          <div className="selection-detail">
            <span className={selectedNode.type === 'Document' ? 'legend-document' : selectedNode.type === 'Passage' ? 'legend-passage' : 'legend-entity'} />
            <span>{selectedNode.type}</span>
            <strong>{selectedNode.label}</strong>
            <button type="button" onClick={() => setSelectedNode(null)} aria-label="Clear selected node">×</button>
          </div>
        )}
        {selectedEdge && (
          <article className="evidence-detail" aria-label="Relationship evidence">
            <div className="evidence-heading">
              <div>
                <p className="eyebrow">RELATIONSHIP EVIDENCE</p>
                <h3>{selectedEdge.label}</h3>
              </div>
              <button type="button" onClick={() => setSelectedEdge(null)} aria-label="Close relationship evidence">×</button>
            </div>
            <blockquote>{selectedEdge.evidence}</blockquote>
            <div className="evidence-meta">
              <span>Page <strong>{selectedEdge.page ?? 'n/a'}</strong></span>
              <span>Confidence <strong>{selectedEdge.confidence === undefined ? 'n/a' : `${Math.round(selectedEdge.confidence * 100)}%`}</strong></span>
              <span>Status <strong className={`review-status ${selectedEdge.status ?? ''}`}>{selectedEdge.status ?? 'n/a'}</strong></span>
              <span>Passage <strong>{selectedEdge.passageId ?? 'n/a'}</strong></span>
            </div>
            {selectedEdge.verificationReason && <p className="verification-reason">{selectedEdge.verificationReason}</p>}
          </article>
        )}
      </section>
      <footer className="footer"><span>DOCUMENT → ENTITY → RELATIONSHIP</span><span>Powered by Neo4j</span></footer>
    </main>
  );
}

export default App;
