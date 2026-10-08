import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D, { ForceGraph3DInstance } from '3d-force-graph';
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
  documentName?: string;
};
type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };
type AskResponse = { answer: string; path: GraphData };
type DocumentSummary = { document_name: string; passage_count: number; concept_count: number; relationship_count: number };
type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  evidence?: GraphEdge[];
  answerPath?: GraphData;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const MAX_VISIBLE_NODES = 180;

const COLORS = {
  document: '#195d4b',
  concept: '#9fd873',
  passage: '#e9b85f',
  highlight: '#d17b20',
  edge: '#9baba5',
  edgePending: '#cdd6d0',
};

function edgeKey(edge: GraphEdge) {
  return `${edge.source}|${edge.target}|${edge.label}|${edge.passageId ?? ''}`;
}

async function readJson(response: Response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

/* ---------- 3D graph (wraps 3d-force-graph) ---------- */

type GraphViewProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodeIds: Set<string>;
  highlightedEdgeKeys: Set<string>;
  onEdgeSelect: (edge: GraphEdge | null) => void;
};

type ViewLink = { source: string; target: string; key: string; edge: GraphEdge };

function GraphView({ nodes, edges, highlightedNodeIds, highlightedEdgeKeys, onEdgeSelect }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraph3DInstance | null>(null);
  const onEdgeSelectRef = useRef(onEdgeSelect);
  onEdgeSelectRef.current = onEdgeSelect;

  // Create the graph once.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const graph = new ForceGraph3D(element)
      .backgroundColor('#fbfcf8')
      .width(element.clientWidth)
      .height(element.clientHeight)
      .nodeRelSize(5)
      .nodeLabel((n) => {
        const node = n as GraphNode;
        return `${node.label} (${node.type})`;
      })
      .linkLabel((l) => {
        const link = l as ViewLink;
        return link.edge.evidence ? `${link.edge.label}: ${link.edge.evidence}` : link.edge.label;
      })
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .onLinkClick((l) => onEdgeSelectRef.current((l as ViewLink).edge))
      .onBackgroundClick(() => onEdgeSelectRef.current(null))
      .onNodeClick((n) => {
        const node = n as { x?: number; y?: number; z?: number };
        if (node.x === undefined || node.y === undefined || node.z === undefined) return;
        const distance = 120;
        const ratio = 1 + distance / Math.hypot(node.x, node.y, node.z);
        graph.cameraPosition(
          { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
          node as { x: number; y: number; z: number },
          800,
        );
      });

    graphRef.current = graph;

    const observer = new ResizeObserver(() => {
      graph.width(element.clientWidth).height(element.clientHeight);
    });
    observer.observe(element);

    return () => {
      observer.disconnect();
      graph._destructor();
      element.replaceChildren();
      graphRef.current = null;
    };
  }, []);

  // Feed data. Copies are passed because the library mutates nodes and links.
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const links: ViewLink[] = edges
      .filter((edge) => edge.status !== 'rejected')
      .map((edge) => ({ source: edge.source, target: edge.target, key: edgeKey(edge), edge }));
    graph.graphData({ nodes: nodes.map((node) => ({ ...node })), links });
  }, [nodes, edges]);

  // Colours and widths react to the highlighted answer path.
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const hasPath = highlightedNodeIds.size > 0;

    graph
      .nodeColor((n) => {
        const node = n as GraphNode;
        if (highlightedNodeIds.has(node.id)) return COLORS.highlight;
        if (node.type === 'Document') return COLORS.document;
        if (node.type === 'Passage') return COLORS.passage;
        return COLORS.concept;
      })
      .nodeOpacity(hasPath ? 0.95 : 0.9)
      .linkColor((l) => {
        const link = l as ViewLink;
        if (highlightedEdgeKeys.has(link.key)) return COLORS.highlight;
        return link.edge.status === 'pending' ? COLORS.edgePending : COLORS.edge;
      })
      .linkWidth((l) => (highlightedEdgeKeys.has((l as ViewLink).key) ? 3 : 0.6))
      .linkDirectionalParticles((l) => (highlightedEdgeKeys.has((l as ViewLink).key) ? 3 : 0))
      .linkDirectionalParticleWidth(3);

    if (hasPath) {
      const timer = window.setTimeout(
        () => graph.zoomToFit(700, 80, (n) => highlightedNodeIds.has((n as GraphNode).id)),
        900,
      );
      return () => window.clearTimeout(timer);
    }
  }, [highlightedNodeIds, highlightedEdgeKeys, nodes, edges]);

  return <div className="graph-3d" ref={containerRef} aria-label="Interactive 3D knowledge graph" />;
}

function AnswerPathGraph({ path, onEdgeSelect }: { path: GraphData; onEdgeSelect: (edge: GraphEdge | null) => void }) {
  const highlightedNodeIds = useMemo(() => new Set(path.nodes.map((node) => node.id)), [path.nodes]);
  const highlightedEdgeKeys = useMemo(() => new Set(path.edges.map(edgeKey)), [path.edges]);

  if (path.nodes.length === 0 || path.edges.length === 0) {
    return (
      <div className="answer-graph-empty">
        No connected graph path was found for this answer.
      </div>
    );
  }

  return (
    <div className="answer-graph">
      <div className="answer-graph-heading">
        <strong>Answer graph</strong>
        <span>{path.nodes.length} concepts · {path.edges.length} connections</span>
      </div>
      <GraphView
        nodes={path.nodes}
        edges={path.edges}
        highlightedNodeIds={highlightedNodeIds}
        highlightedEdgeKeys={highlightedEdgeKeys}
        onEdgeSelect={onEdgeSelect}
      />
    </div>
  );
}

/* ---------- App ---------- */

function App() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocument, setSelectedDocument] = useState('');
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 1) Find uploaded documents and pick one (?document_name=... wins, else the first with relationships).
  useEffect(() => {
    let cancelled = false;
    const requested = new URLSearchParams(window.location.search).get('document_name');
    fetch(`${API_BASE_URL}/api/graph/summary`)
      .then(async (response) => {
        const result = await readJson(response);
        if (!response.ok) throw new Error(result.detail ?? 'Could not load the document list.');
        return (result.documents ?? []) as DocumentSummary[];
      })
      .then((docs) => {
        if (cancelled) return;
        setDocuments(docs);
        setSelectedDocument(
          requested ?? docs.find((doc) => doc.relationship_count > 0)?.document_name ?? docs[0]?.document_name ?? '',
        );
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setGraphError(error instanceof Error ? error.message : 'Could not load the document list.');
        if (requested) setSelectedDocument(requested);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2) Load the full graph of the selected document.
  useEffect(() => {
    if (!selectedDocument) return;
    let cancelled = false;
    setGraphError(null);
    fetch(`${API_BASE_URL}/api/graph/graph?document_name=${encodeURIComponent(selectedDocument)}`)
      .then(async (response) => {
        const result = await readJson(response);
        if (!response.ok) throw new Error(result.detail ?? 'Could not load this graph.');
        return result as GraphData;
      })
      .then((result) => {
        if (!cancelled) setGraph(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setGraphError(error instanceof Error ? error.message : 'Could not load this graph.');
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDocument]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isAsking]);

  // Merge the stored graph with the answer path so the path is always visible.
  const visibleGraph = useMemo(() => {
    if (!graph && !askResult) return null;
    const graphNodes = graph?.nodes ?? [];
    const graphEdges = graph?.edges ?? [];
    const pathNodes = askResult?.path.nodes ?? [];
    const highlightedNodeIds = new Set(pathNodes.map((node) => node.id));
    const highlightedEdgeKeys = new Set((askResult?.path.edges ?? []).map(edgeKey));

    const firstNodes = [...new Map([...pathNodes, ...graphNodes.filter((n) => highlightedNodeIds.has(n.id))].map((n) => [n.id, n])).values()];
    const otherNodes = graphNodes.filter((node) => !highlightedNodeIds.has(node.id));
    const nodes = [...firstNodes, ...otherNodes].slice(0, MAX_VISIBLE_NODES);
    const visibleIds = new Set(nodes.map((node) => node.id));

    const allEdges = [...graphEdges];
    const existing = new Set(allEdges.map(edgeKey));
    for (const edge of askResult?.path.edges ?? []) {
      if (!existing.has(edgeKey(edge))) allEdges.push(edge);
    }
    const edges = allEdges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    return { nodes, edges, highlightedNodeIds, highlightedEdgeKeys };
  }, [graph, askResult]);

  const labelById = useMemo(
    () => new Map((visibleGraph?.nodes ?? []).map((node) => [node.id, node.label])),
    [visibleGraph],
  );

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || isAsking) return;

    setMessages((current) => [...current, { role: 'user', content: submittedQuestion }]);
    setQuestion('');
    setIsAsking(true);
    setAskResult(null);
    setSelectedEdge(null);
    try {
      const response = await fetch(`${API_BASE_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: submittedQuestion }),
      });
      const result = await readJson(response);
      if (!response.ok) throw new Error(result.detail ?? 'The question could not be answered.');

      const answer = result as AskResponse;
      const path: GraphData = { nodes: answer.path?.nodes ?? [], edges: answer.path?.edges ?? [] };
      setAskResult({ answer: answer.answer, path });
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: answer.answer,
          evidence: path.edges.filter((edge) => edge.evidence),
          answerPath: path,
        },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The question could not be answered.';
      setMessages((current) => [...current, { role: 'assistant', content: message }]);
    } finally {
      setIsAsking(false);
    }
  }

  const hasGraph = !!visibleGraph && visibleGraph.nodes.length > 0;

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
          <p className="eyebrow">EVIDENCE-BASED GRAPH Q&A</p>
          <h1>Ask a question.<br />Explore the answer.</h1>
        </div>
        <p className="intro-copy">Ask about the knowledge graph to get a concise answer and see the connected concepts highlighted below.</p>
      </section>

      <section className="chat-panel" aria-label="Ask the knowledge graph">
        <div className="chat-heading">
          <div>
            <p className="eyebrow">CHAT</p>
            <h2>Ask your graph</h2>
          </div>
          <span>Answers use verified graph evidence</span>
        </div>
        {messages.length > 0 && (
          <div className="chat-messages" aria-live="polite">
            {messages.map((message, index) => (
              <article className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span className="chat-role">{message.role === 'user' ? 'You' : 'Graph assistant'}</span>
                <p>{message.content}</p>
                {message.role === 'assistant' && message.answerPath && (
                  <AnswerPathGraph path={message.answerPath} onEdgeSelect={setSelectedEdge} />
                )}
                {message.evidence && message.evidence.length > 0 && (
                  <details className="chat-evidence">
                    <summary>Evidence ({message.evidence.length})</summary>
                    {message.evidence.map((edge) => (
                      <blockquote key={edgeKey(edge)}>
                        <span>
                          {labelById.get(edge.source) ?? edge.source} → {edge.label} → {labelById.get(edge.target) ?? edge.target}
                        </span>
                        <q>{edge.evidence}</q>
                        {(edge.page !== undefined || edge.documentName) && (
                          <small>
                            {edge.documentName}
                            {edge.page !== undefined ? ` · page ${edge.page}` : ''}
                          </small>
                        )}
                      </blockquote>
                    ))}
                  </details>
                )}
              </article>
            ))}
            {isAsking && <p className="chat-thinking"><span className="spinner" /> Finding graph evidence…</p>}
            <div ref={messagesEndRef} />
          </div>
        )}
        <form className="chat-form" onSubmit={handleAsk}>
          <label className="visually-hidden" htmlFor="graph-question">Question</label>
          <input
            id="graph-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask how two concepts are connected…"
            maxLength={2000}
            disabled={isAsking}
          />
          <button className="process-button" type="submit" disabled={!question.trim() || isAsking}>
            {isAsking ? <span className="spinner" /> : <span aria-hidden="true">↗</span>}
            Ask
          </button>
        </form>
      </section>

      <section className="graph-section" aria-label="Generated graph">
        <div className="graph-heading">
          <div>
            <p className="eyebrow">ANSWER GRAPH</p>
            <h2>Connected concepts</h2>
          </div>
          {documents.length > 0 && (
            <label className="doc-picker">
              <span>Document</span>
              <select value={selectedDocument} onChange={(event) => setSelectedDocument(event.target.value)}>
                {documents.map((doc) => (
                  <option key={doc.document_name} value={doc.document_name}>
                    {doc.document_name} ({doc.relationship_count} links)
                  </option>
                ))}
              </select>
            </label>
          )}
          {visibleGraph && (
            <div className="graph-stats">
              <span><b>{visibleGraph.nodes.length}</b> nodes</span>
              <span><b>{visibleGraph.edges.length}</b> connections</span>
            </div>
          )}
        </div>

        <div className={`graph-canvas ${hasGraph ? 'populated is-3d' : ''}`}>
          {hasGraph && visibleGraph ? (
            <>
              <GraphView
                nodes={visibleGraph.nodes}
                edges={visibleGraph.edges}
                highlightedNodeIds={visibleGraph.highlightedNodeIds}
                highlightedEdgeKeys={visibleGraph.highlightedEdgeKeys}
                onEdgeSelect={setSelectedEdge}
              />
              <p className="graph-hint">Drag to rotate · scroll to zoom · click a connection to see its evidence</p>
            </>
          ) : (
            <div className="empty-graph">
              <div className="empty-mark" aria-hidden="true"><span /><span /><span /><span /></div>
              <strong>Your answer graph will appear here</strong>
              <span>Ask a question to see its relevant concepts and connections.</span>
            </div>
          )}
          {graph && graph.nodes.length > MAX_VISIBLE_NODES && (
            <p className="graph-limit">Showing {MAX_VISIBLE_NODES} of {graph.nodes.length} nodes for a responsive view.</p>
          )}
        </div>

        {graphError && <p className="graph-error" role="alert">{graphError}</p>}

        {hasGraph && (
          <div className="graph-legend" aria-label="Legend">
            <span><i className="legend-document" /> Document</span>
            <span><i className="legend-entity" /> Concept</span>
            <span><i className="legend-passage" /> Passage</span>
            <span><i className="legend-path" /> Answer path</span>
          </div>
        )}

        {selectedEdge && (
          <aside className="evidence-detail" aria-label="Relationship evidence">
            <div className="evidence-heading">
              <div>
                <p className="eyebrow">EVIDENCE</p>
                <h3>
                  {labelById.get(selectedEdge.source) ?? selectedEdge.source} → {selectedEdge.label} →{' '}
                  {labelById.get(selectedEdge.target) ?? selectedEdge.target}
                </h3>
              </div>
              <button type="button" onClick={() => setSelectedEdge(null)} aria-label="Close evidence">×</button>
            </div>
            {selectedEdge.evidence ? (
              <blockquote>{selectedEdge.evidence}</blockquote>
            ) : (
              <p className="verification-reason">This connection has no stored evidence quote.</p>
            )}
            <div className="evidence-meta">
              {selectedEdge.documentName && <span>Document<strong>{selectedEdge.documentName}</strong></span>}
              {selectedEdge.page !== undefined && <span>Page<strong>{selectedEdge.page}</strong></span>}
              {selectedEdge.passageId && <span>Passage<strong>{selectedEdge.passageId}</strong></span>}
              {selectedEdge.confidence !== undefined && <span>Confidence<strong>{selectedEdge.confidence.toFixed(2)}</strong></span>}
              {selectedEdge.status && (
                <span>Status<strong className={`review-status ${selectedEdge.status}`}>{selectedEdge.status}</strong></span>
              )}
            </div>
            {selectedEdge.verificationReason && <p className="verification-reason">{selectedEdge.verificationReason}</p>}
          </aside>
        )}
      </section>
      <footer className="footer"><span>DOCUMENT → ENTITY → RELATIONSHIP</span><span>Powered by Neo4j</span></footer>
    </main>
  );
}

export default App;
