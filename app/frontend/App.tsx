import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D, { ForceGraph3DInstance } from '3d-force-graph';
import './App.css';

type EvidenceRecord = {
  document_name?: string;
  passage_id?: string;
  page?: number;
  evidence?: string;
  confidence?: number;
  status?: string;
};

type GraphNode = {
  id: string;
  label: string;
  type: 'Document' | 'Concept' | 'Passage' | string;
  entity_type?: string;
  community_id?: number;
  aliases?: string[];
  documents?: string[];
  page?: number;
};

type GraphEdge = {
  source: string;
  target: string;
  label: string;
  evidence?: string;
  evidence_list?: string[];
  evidence_records?: EvidenceRecord[];
  passageId?: string;
  passage_ids?: string[];
  page?: number;
  confidence?: number;
  status?: 'verified' | 'pending' | 'rejected' | string;
  verificationReason?: string;
  documentName?: string;
  document_names?: string[];
  collection_id?: string;
};

type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };
type AskResponse = { answer: string; path: GraphData };

type CollectionSummary = {
  collection_id: string;
  name: string;
  description?: string;
  document_count: number;
  concept_count: number;
  relationship_count: number;
};

type DocumentSummary = {
  document_name: string;
  collection_id?: string;
  passage_count: number;
  concept_count: number;
  relationship_count: number;
};

type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  evidence?: GraphEdge[];
  answerPath?: GraphData;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const LARGE_GRAPH_THRESHOLD = 240;

const COLORS: Record<string, string> = {
  document: '#195d4b',
  passage: '#e9b85f',
  concept: '#8bc34a',
  BiologicalEntity: '#2e7d32',
  ChemicalEntity: '#00838f',
  Process: '#6a1b9a',
  Organization: '#283593',
  Person: '#ad1457',
  Location: '#ef6c00',
  Method: '#4e342e',
  highlight: '#d17b20',
  edge: '#9baba5',
  edgePending: '#cdd6d0',
};

const COMMUNITY_PALETTE = [
  '#2e7d32', '#1565c0', '#6a1b9a', '#c2185b', '#e65100',
  '#00838f', '#4e342e', '#37474f', '#558b2f', '#f57f17',
];

function edgeKey(edge: GraphEdge) {
  const pId = edge.passageId ?? (edge.passage_ids?.[0] ?? '');
  return `${edge.source}|${edge.target}|${edge.label}|${pId}`;
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
  selectedNodeId?: string | null;
  onEdgeSelect: (edge: GraphEdge | null) => void;
  onNodeSelect?: (node: GraphNode | null) => void;
};

type ViewLink = { source: string; target: string; key: string; edge: GraphEdge };

function GraphView({
  nodes,
  edges,
  highlightedNodeIds,
  highlightedEdgeKeys,
  selectedNodeId,
  onEdgeSelect,
  onNodeSelect,
}: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraph3DInstance | null>(null);
  const onEdgeSelectRef = useRef(onEdgeSelect);
  const onNodeSelectRef = useRef(onNodeSelect);
  onEdgeSelectRef.current = onEdgeSelect;
  onNodeSelectRef.current = onNodeSelect;

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
        const eType = node.entity_type && node.entity_type !== 'Concept' ? ` [${node.entity_type}]` : '';
        const comm = node.community_id !== undefined ? ` (Group ${node.community_id + 1})` : '';
        return `${node.label} (${node.type})${eType}${comm}`;
      })
      .linkLabel((l) => {
        const link = l as ViewLink;
        return link.edge.evidence ? `${link.edge.label}: ${link.edge.evidence}` : link.edge.label;
      })
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .onLinkClick((l) => onEdgeSelectRef.current((l as ViewLink).edge))
      .onBackgroundClick(() => {
        onEdgeSelectRef.current(null);
        onNodeSelectRef.current?.(null);
      })
      .onNodeClick((n) => {
        const node = n as GraphNode & { x?: number; y?: number; z?: number };
        if (node.x !== undefined && node.y !== undefined && node.z !== undefined) {
          const distance = 120;
          const ratio = 1 + distance / Math.hypot(node.x, node.y, node.z);
          graph.cameraPosition(
            { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
            node as { x: number; y: number; z: number },
            800,
          );
        }
        onNodeSelectRef.current?.(node);
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

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const links: ViewLink[] = edges
      .filter((edge) => edge.status !== 'rejected')
      .map((edge) => ({ source: edge.source, target: edge.target, key: edgeKey(edge), edge }));
    graph.graphData({ nodes: nodes.map((node) => ({ ...node })), links });
  }, [nodes, edges]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const hasPath = highlightedNodeIds.size > 0;

    graph
      .nodeColor((n) => {
        const node = n as GraphNode;
        if (selectedNodeId && node.id === selectedNodeId) return COLORS.highlight;
        if (highlightedNodeIds.has(node.id)) return COLORS.highlight;
        if (node.type === 'Document') return COLORS.document;
        if (node.type === 'Passage') return COLORS.passage;
        if (node.entity_type && COLORS[node.entity_type]) return COLORS[node.entity_type];
        if (node.community_id !== undefined && node.community_id >= 0) {
          return COMMUNITY_PALETTE[node.community_id % COMMUNITY_PALETTE.length];
        }
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
  }, [highlightedNodeIds, highlightedEdgeKeys, nodes, edges, selectedNodeId]);

  return <div className="graph-3d" ref={containerRef} aria-label="Interactive 3D knowledge graph" />;
}

function AnswerPathGraph({
  path,
  onEdgeSelect,
  onNodeSelect,
  selectedNodeId,
}: {
  path: GraphData;
  onEdgeSelect: (edge: GraphEdge | null) => void;
  onNodeSelect?: (node: GraphNode | null) => void;
  selectedNodeId?: string | null;
}) {
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
        selectedNodeId={selectedNodeId}
        onEdgeSelect={onEdgeSelect}
        onNodeSelect={onNodeSelect}
      />
    </div>
  );
}

/* ---------- Main App Component ---------- */

function App() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>('default');
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<string>('');
  const [selectedCommunity, setSelectedCommunity] = useState<string>('all');
  const [nodeSearch, setNodeSearch] = useState('');
  const [isCreatingCollection, setIsCreatingCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState('');
  const [newCollectionDesc, setNewCollectionDesc] = useState('');

  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ type: 'idle' | 'loading' | 'success' | 'error'; message: string }>({
    type: 'idle',
    message: '',
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 1) Fetch Summary (Collections + Documents)
  const refreshSummary = async (preferredColId?: string, preferredDocName?: string) => {
    const response = await fetch(`${API_BASE_URL}/api/graph/summary`);
    const result = await readJson(response);
    if (!response.ok) throw new Error(result.detail ?? 'Could not load collections summary.');

    const cols = (result.collections ?? []) as CollectionSummary[];
    const docs = (result.documents ?? []) as DocumentSummary[];

    setCollections(cols);
    setDocuments(docs);

    const activeColId = preferredColId || selectedCollectionId || cols[0]?.collection_id || 'default';
    setSelectedCollectionId(activeColId);

    if (preferredDocName !== undefined) {
      setSelectedDocument(preferredDocName);
    }

    return { cols, docs, activeColId };
  };

  useEffect(() => {
    let cancelled = false;
    refreshSummary().catch((error: unknown) => {
      if (!cancelled) setGraphError(error instanceof Error ? error.message : 'Could not load summary.');
    });
    return () => { cancelled = true; };
  }, []);

  // 2) Load Combined Graph for Selected Collection / Document
  useEffect(() => {
    if (!selectedCollectionId) return;
    let cancelled = false;
    setGraphError(null);

    let url = `${API_BASE_URL}/api/graph/graph?collection_id=${encodeURIComponent(selectedCollectionId)}`;
    if (selectedDocument) {
      url += `&document_name=${encodeURIComponent(selectedDocument)}`;
    }
    if (selectedCommunity !== 'all') {
      url += `&community_id=${encodeURIComponent(selectedCommunity)}`;
    }

    fetch(url)
      .then(async (response) => {
        const result = await readJson(response);
        if (!response.ok) throw new Error(result.detail ?? 'Could not load the graph.');
        return result as GraphData;
      })
      .then((result) => {
        if (!cancelled) setGraph(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setGraphError(error instanceof Error ? error.message : 'Could not load this graph.');
      });

    return () => { cancelled = true; };
  }, [selectedCollectionId, selectedDocument, selectedCommunity]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isAsking]);

  // Merge graph with answer path while preserving important bridge nodes rather than slicing arbitrarily.
  const visibleGraph = useMemo(() => {
    if (!graph && !askResult) return null;
    const graphNodes = graph?.nodes ?? [];
    const graphEdges = graph?.edges ?? [];
    const pathNodes = askResult?.path.nodes ?? [];
    const highlightedNodeIds = new Set(pathNodes.map((n) => n.id));
    const highlightedEdgeKeys = new Set((askResult?.path.edges ?? []).map(edgeKey));
    const adjacency = new Map<string, Set<string>>();

    for (const node of graphNodes) adjacency.set(node.id, new Set());
    for (const edge of graphEdges) {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
      adjacency.get(edge.source)?.add(edge.target);
      adjacency.get(edge.target)?.add(edge.source);
    }

    const searchTerm = nodeSearch.trim().toLowerCase();
    const includeIds = new Set<string>([...highlightedNodeIds, ...(selectedNode ? [selectedNode.id] : [])]);

    if (searchTerm) {
      for (const node of graphNodes) {
        if (node.label.toLowerCase().includes(searchTerm)) includeIds.add(node.id);
      }
    }

    if (graphNodes.length <= LARGE_GRAPH_THRESHOLD) {
      for (const node of graphNodes) includeIds.add(node.id);
    } else {
      const ranked = [...graphNodes].sort((a, b) => {
        const degreeA = adjacency.get(a.id)?.size ?? 0;
        const degreeB = adjacency.get(b.id)?.size ?? 0;
        return degreeB - degreeA || a.label.localeCompare(b.label);
      });

      for (const node of ranked.slice(0, 180)) includeIds.add(node.id);
      for (const id of Array.from(includeIds)) {
        for (const neighbor of adjacency.get(id) ?? []) includeIds.add(neighbor);
      }
    }

    for (const node of pathNodes) includeIds.add(node.id);

    const nodes = graphNodes.filter((node) => includeIds.has(node.id));
    const visibleIds = new Set(nodes.map((node) => node.id));

    const allEdges = [...graphEdges];
    const existing = new Set(allEdges.map(edgeKey));
    for (const edge of askResult?.path.edges ?? []) {
      if (!existing.has(edgeKey(edge))) allEdges.push(edge);
    }
    const edges = allEdges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    return { nodes, edges, highlightedNodeIds, highlightedEdgeKeys };
  }, [graph, askResult, nodeSearch, selectedNode]);

  const graphStats = useMemo(() => {
    if (!graph) return { totalNodes: 0, totalEdges: 0, disconnectedComponents: 0, isolatedConcepts: 0 };

    const conceptNodes = graph.nodes.filter((node) => node.type === 'Concept');
    const adjacency = new Map<string, Set<string>>();
    for (const node of conceptNodes) adjacency.set(node.id, new Set());
    for (const edge of graph.edges) {
      if (adjacency.has(edge.source) && adjacency.has(edge.target)) {
        adjacency.get(edge.source)?.add(edge.target);
        adjacency.get(edge.target)?.add(edge.source);
      }
    }

    const visited = new Set<string>();
    let components = 0;
    for (const node of conceptNodes) {
      if (visited.has(node.id)) continue;
      components += 1;
      const stack = [node.id];
      while (stack.length > 0) {
        const current = stack.pop();
        if (!current || visited.has(current)) continue;
        visited.add(current);
        for (const neighbor of adjacency.get(current) ?? []) {
          if (!visited.has(neighbor)) stack.push(neighbor);
        }
      }
    }

    const isolatedConcepts = conceptNodes.filter((node) => (adjacency.get(node.id)?.size ?? 0) === 0).length;
    return {
      totalNodes: graph.nodes.length,
      totalEdges: graph.edges.length,
      disconnectedComponents: Math.max(components, 1),
      isolatedConcepts,
    };
  }, [graph]);

  const labelById = useMemo(
    () => new Map((visibleGraph?.nodes ?? []).map((node) => [node.id, node.label])),
    [visibleGraph],
  );

  // Available communities in current graph
  const communities = useMemo(() => {
    const set = new Set<number>();
    (visibleGraph?.nodes ?? []).forEach((n) => {
      if (n.community_id !== undefined && n.community_id >= 0) set.add(n.community_id);
    });
    return Array.from(set).sort((a, b) => a - b);
  }, [visibleGraph]);

  // Documents in currently selected collection
  const collectionDocs = useMemo(() => {
    return documents.filter((d) => !d.collection_id || d.collection_id === selectedCollectionId);
  }, [documents, selectedCollectionId]);

  // Collection creation
  async function handleCreateCollection(event: FormEvent) {
    event.preventDefault();
    if (!newCollectionName.trim()) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/graph/collections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newCollectionName.trim(),
          description: newCollectionDesc.trim() || undefined,
        }),
      });
      const result = await readJson(response);
      if (!response.ok) throw new Error(result.detail ?? 'Could not create collection.');

      const newId = result.id || newCollectionName.toLowerCase().trim().replace(/\s+/g, '_');
      setNewCollectionName('');
      setNewCollectionDesc('');
      setIsCreatingCollection(false);
      await refreshSummary(newId, '');
    } catch (error) {
      setGraphError(error instanceof Error ? error.message : 'Could not create collection.');
    }
  }

  // Ask Question
  async function askQuestion(submittedQuestion: string) {
    const trimmed = submittedQuestion.trim();
    if (!trimmed || isAsking) return;

    setMessages((cur) => [...cur, { role: 'user', content: trimmed }]);
    setQuestion('');
    setIsAsking(true);
    setAskResult(null);
    setSelectedEdge(null);

    try {
      const response = await fetch(`${API_BASE_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: trimmed,
          collection_id: selectedCollectionId || undefined,
        }),
      });
      const result = await readJson(response);
      if (!response.ok) throw new Error(result.detail ?? 'The question could not be answered.');

      const answer = result as AskResponse;
      const path: GraphData = { nodes: answer.path?.nodes ?? [], edges: answer.path?.edges ?? [] };
      setAskResult({ answer: answer.answer, path });
      setMessages((cur) => [
        ...cur,
        {
          role: 'assistant',
          content: answer.answer,
          evidence: path.edges.filter((e) => e.evidence),
          answerPath: path,
        },
      ]);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'The question could not be answered.';
      setMessages((cur) => [...cur, { role: 'assistant', content: msg }]);
    } finally {
      setIsAsking(false);
    }
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) {
      if (selectedNode) {
        await askQuestion(`Explain the concept "${selectedNode.label}" in the context of collection "${selectedCollectionId}".`);
      }
      return;
    }
    await askQuestion(question.trim());
  }

  // Upload Document into Selected Collection
  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadFile || isUploading) return;

    setIsUploading(true);
    const activeColName = collections.find((c) => c.collection_id === selectedCollectionId)?.name || selectedCollectionId;
    setUploadStatus({
      type: 'loading',
      message: `Uploading "${uploadFile.name}" into collection "${activeColName}" and generating graph…`,
    });
    setGraphError(null);

    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('collection_id', selectedCollectionId);
    formData.append('collection_name', activeColName);

    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      });
      const result = await readJson(response);
      if (!response.ok) throw new Error(result.detail ?? 'The document could not be processed.');

      const filename = uploadFile.name;
      setUploadStatus({
        type: 'success',
        message: result.message ?? `"${filename}" was processed successfully into collection "${activeColName}".`,
      });
      setUploadFile(null);
      await refreshSummary(selectedCollectionId, '');
      setMessages((cur) => [
        ...cur,
        {
          role: 'assistant',
          content: `Document "${filename}" was successfully added to collection "${activeColName}". The combined collection graph is ready for queries.`,
        },
      ]);
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'The document could not be processed.';
      setGraphError(msg);
      setUploadStatus({ type: 'error', message: msg });
    } finally {
      setIsUploading(false);
    }
  }

  const hasGraph = !!visibleGraph && visibleGraph.nodes.length > 0;
  const activeCollection = collections.find((c) => c.collection_id === selectedCollectionId);

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Graphroom home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>Graphroom · Multi-Document GraphRAG</span>
        </a>
        <span className="connection"><span className="connection-dot" /> NEO4J KNOWLEDGE ENGINE</span>
      </header>

      <section className="intro" id="top">
        <div>
          <p className="eyebrow">COLLECTION-BASED EVIDENCE GRAPH</p>
          <h1>Create collections.<br />Connect related documents.</h1>
        </div>
        <p className="intro-copy">
          Upload documents individually into subject collections. Concepts, entities, and relationships combine automatically across documents through shared canonical entities.
        </p>
      </section>

      {/* Collection Selection Toolbar */}
      <section className="collection-toolbar" aria-label="Collection management">
        <div className="collection-picker-group">
          <label className="collection-picker">
            <span>Subject Collection:</span>
            <select
              value={selectedCollectionId}
              onChange={(e) => {
                setSelectedCollectionId(e.target.value);
                setSelectedDocument('');
                setSelectedCommunity('all');
                setSelectedNode(null);
                setSelectedEdge(null);
              }}
            >
              {collections.map((col) => (
                <option key={col.collection_id} value={col.collection_id}>
                  {col.name} ({col.document_count} docs · {col.relationship_count} relations)
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setIsCreatingCollection(!isCreatingCollection)}
          >
            {isCreatingCollection ? 'Cancel' : '+ New Collection'}
          </button>
        </div>

        {activeCollection && (
          <span className="collection-badge">
            Collection: <strong>{activeCollection.name}</strong>
          </span>
        )}
      </section>

      {/* Collection Creation Form */}
      {isCreatingCollection && (
        <form className="collection-create-panel" onSubmit={handleCreateCollection}>
          <input
            placeholder="Collection Name (e.g. Cell Biology)"
            value={newCollectionName}
            onChange={(e) => setNewCollectionName(e.target.value)}
            required
          />
          <input
            placeholder="Optional description"
            value={newCollectionDesc}
            onChange={(e) => setNewCollectionDesc(e.target.value)}
          />
          <button type="submit" className="process-button">Create</button>
        </form>
      )}

      {/* Ingestion Section */}
      <section className="ingest" aria-label="Upload document into collection">
        <form className="upload-form" onSubmit={handleUpload}>
          <label className={`file-picker ${uploadFile ? 'has-file' : ''}`}>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
            />
            <span className="upload-glyph" aria-hidden="true">⇪</span>
            <span className="file-copy">
              <strong>{uploadFile ? uploadFile.name : `Choose PDF, DOCX, or TXT for "${activeCollection?.name ?? 'Collection'}"`}</strong>
              <small>Uploads are merged into the active collection graph with canonical entity resolution</small>
            </span>
            <span className="browse-label">Browse</span>
          </label>
          <button className="process-button" type="submit" disabled={!uploadFile || isUploading}>
            {isUploading ? <span className="spinner" /> : <span aria-hidden="true">↗</span>}
            {isUploading ? 'Ingesting…' : 'Add to collection'}
          </button>
        </form>
        {uploadStatus.message && (
          <p className={`status ${uploadStatus.type === 'success' ? 'success' : ''}`}>
            {uploadStatus.message}
          </p>
        )}
      </section>

      {/* Chat Section */}
      <section className="chat-panel" aria-label="Ask the knowledge graph">
        <div className="chat-heading">
          <div>
            <p className="eyebrow">Q&A OVER COLLECTION</p>
            <h2>Ask your collection graph</h2>
          </div>
          <span>Grounded in verified multi-document evidence</span>
        </div>
        {messages.length > 0 && (
          <div className="chat-messages" aria-live="polite">
            {messages.map((message, index) => (
              <article className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span className="chat-role">{message.role === 'user' ? 'You' : 'Graph Assistant'}</span>
                <p>{message.content}</p>
                {message.role === 'assistant' && message.answerPath && (
                  <AnswerPathGraph
                    path={message.answerPath}
                    onEdgeSelect={setSelectedEdge}
                    onNodeSelect={setSelectedNode}
                    selectedNodeId={selectedNode?.id}
                  />
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
            {isAsking && <p className="chat-thinking"><span className="spinner" /> Exploring collection graph…</p>}
            <div ref={messagesEndRef} />
          </div>
        )}
        <form className="chat-form" onSubmit={handleAsk}>
          <label className="visually-hidden" htmlFor="graph-question">Question</label>
          <input
            id="graph-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={selectedNode ? `Ask about "${selectedNode.label}" or across collection...` : `Ask about any concepts in "${activeCollection?.name ?? 'Collection'}"...`}
            maxLength={2000}
            disabled={isAsking}
          />
          <button className="process-button" type="submit" disabled={(!question.trim() && !selectedNode) || isAsking}>
            {isAsking ? <span className="spinner" /> : <span aria-hidden="true">↗</span>}
            Ask
          </button>
        </form>
      </section>

      {/* 3D Knowledge Graph Visualization */}
      <section className="graph-section" aria-label="Generated graph">
        <div className="graph-heading">
          <div>
            <p className="eyebrow">COLLECTION GRAPH VIEW</p>
            <h2>{activeCollection?.name ?? 'Knowledge Graph'}</h2>
          </div>

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Filter by Document */}
            {collectionDocs.length > 0 && (
              <label className="doc-picker">
                <span>View Scope</span>
                <select value={selectedDocument} onChange={(e) => setSelectedDocument(e.target.value)}>
                  <option value="">Combined Collection ({collectionDocs.length} docs)</option>
                  {collectionDocs.map((doc) => (
                    <option key={doc.document_name} value={doc.document_name}>
                      {doc.document_name} ({doc.relationship_count} relations)
                    </option>
                  ))}
                </select>
              </label>
            )}

            {/* Filter by Community */}
            {communities.length > 1 && (
              <label className="community-filter">
                <span>Topic Group:</span>
                <select value={selectedCommunity} onChange={(e) => setSelectedCommunity(e.target.value)}>
                  <option value="all">All Groups ({communities.length})</option>
                  {communities.map((cid) => (
                    <option key={cid} value={cid}>Group {cid + 1}</option>
                  ))}
                </select>
              </label>
            )}

            {graphStats && (
              <div className="graph-stats">
                <span><b>{graphStats.totalNodes}</b> nodes</span>
                <span><b>{graphStats.totalEdges}</b> connections</span>
                <span><b>{graphStats.disconnectedComponents}</b> components</span>
              </div>
            )}
          </div>
        </div>

        <div className={`graph-canvas ${hasGraph ? 'populated is-3d' : ''}`}>
          {hasGraph && visibleGraph ? (
            <>
              <GraphView
                nodes={visibleGraph.nodes}
                edges={visibleGraph.edges}
                highlightedNodeIds={visibleGraph.highlightedNodeIds}
                highlightedEdgeKeys={visibleGraph.highlightedEdgeKeys}
                selectedNodeId={selectedNode?.id}
                onEdgeSelect={setSelectedEdge}
                onNodeSelect={setSelectedNode}
              />
              <p className="graph-hint">Drag to rotate · scroll to zoom · click concept to inspect · click edge to see multi-document evidence</p>
            </>
          ) : (
            <div className="empty-graph">
              <div className="empty-mark" aria-hidden="true"><span /><span /><span /><span /></div>
              <strong>No graph data in this collection yet</strong>
              <span>Upload documents into this collection to generate and view connected concepts.</span>
            </div>
          )}
          {graphStats && graphStats.disconnectedComponents > 1 && (
            <p className="graph-limit">This collection contains {graphStats.disconnectedComponents} disconnected components; bridge nodes are kept to preserve cross-document links.</p>
          )}
        </div>

        {graphError && <p className="graph-error" role="alert">{graphError}</p>}

        {/* Legend */}
        {hasGraph && (
          <div className="graph-legend" aria-label="Legend">
            <span><i className="legend-document" /> Document</span>
            <span><i className="legend-passage" /> Passage</span>
            <span><i className="legend-entity" /> Concept / Entity</span>
            <span><i className="legend-path" /> Answer Path</span>
          </div>
        )}

        {/* Node Inspection Drawer */}
        {selectedNode && (
          <aside className="node-detail" aria-label="Concept inspection">
            <div className="node-detail-header">
              <h3>{selectedNode.label}</h3>
              <button type="button" onClick={() => setSelectedNode(null)} aria-label="Close node details">×</button>
            </div>
            <div className="node-detail-meta">
              <span>Type: <strong>{selectedNode.entity_type || selectedNode.type}</strong></span>
              {selectedNode.community_id !== undefined && (
                <span>Topic Group: <strong>Group {selectedNode.community_id + 1}</strong></span>
              )}
              {selectedNode.aliases && selectedNode.aliases.length > 1 && (
                <span>Aliases: <strong>{selectedNode.aliases.join(', ')}</strong></span>
              )}
            </div>
            {selectedNode.documents && selectedNode.documents.length > 0 && (
              <div style={{ marginTop: '8px' }}>
                <span style={{ fontSize: '11px', color: '#62756c' }}>Mentioned across documents:</span>
                <div className="doc-tags">
                  {selectedNode.documents.map((doc) => (
                    <span className="doc-tag" key={doc}>{doc}</span>
                  ))}
                </div>
              </div>
            )}
          </aside>
        )}

        {/* Edge / Multi-Evidence Inspection Drawer */}
        {selectedEdge && (
          <aside className="evidence-detail" aria-label="Relationship evidence">
            <div className="evidence-heading">
              <div>
                <p className="eyebrow">RELATIONSHIP PROVENANCE</p>
                <h3>
                  {labelById.get(selectedEdge.source) ?? selectedEdge.source} → {selectedEdge.label} →{' '}
                  {labelById.get(selectedEdge.target) ?? selectedEdge.target}
                </h3>
              </div>
              <button type="button" onClick={() => setSelectedEdge(null)} aria-label="Close evidence">×</button>
            </div>

            {/* Multi-Evidence Records */}
            {selectedEdge.evidence_records && selectedEdge.evidence_records.length > 0 ? (
              <div className="evidence-multi-list">
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#354c40' }}>
                  Supported by {selectedEdge.evidence_records.length} passage{selectedEdge.evidence_records.length > 1 ? 's' : ''}:
                </span>
                {selectedEdge.evidence_records.map((rec, idx) => (
                  <div className="evidence-card" key={idx}>
                    <q>{rec.evidence}</q>
                    <div className="evidence-card-meta">
                      {rec.document_name && <span>Document: <strong>{rec.document_name}</strong></span>}
                      {rec.page !== undefined && <span>Page: <strong>{rec.page}</strong></span>}
                      {rec.passage_id && <span>Passage: <strong>{rec.passage_id.slice(0, 8)}</strong></span>}
                      {rec.confidence !== undefined && <span>Confidence: <strong>{rec.confidence.toFixed(2)}</strong></span>}
                      {rec.status && <span>Status: <strong className={`review-status ${rec.status}`}>{rec.status}</strong></span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : selectedEdge.evidence ? (
              <blockquote>{selectedEdge.evidence}</blockquote>
            ) : (
              <p className="verification-reason">This connection has no stored evidence quote.</p>
            )}

            <div className="evidence-meta" style={{ marginTop: '12px' }}>
              {selectedEdge.document_names && selectedEdge.document_names.length > 0 && (
                <span>Supporting Documents: <strong>{selectedEdge.document_names.join(', ')}</strong></span>
              )}
              {selectedEdge.confidence !== undefined && (
                <span>Max Confidence: <strong>{selectedEdge.confidence.toFixed(2)}</strong></span>
              )}
              {selectedEdge.status && (
                <span>Status: <strong className={`review-status ${selectedEdge.status}`}>{selectedEdge.status}</strong></span>
              )}
            </div>
          </aside>
        )}
      </section>

      <footer className="footer">
        <span>COLLECTION → DOCUMENT → CANONICAL ENTITY → MULTI-EVIDENCE RELATIONSHIP</span>
        <span>Powered by Neo4j & GraphRAG</span>
      </footer>
    </main>
  );
}

export default App;
