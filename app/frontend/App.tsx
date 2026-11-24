import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  CollectionSummary,
  DocumentSummary,
  GraphData,
  GraphNode,
  GraphEdge,
  GraphStats,
  ChatMessage,
  AskResponse,
  TopicGroup,
  KeyTerm,
} from './src/types/graph';
import { api } from './src/services/api';
import { edgeKey } from './src/components/Graph/ForceGraphView';
import { Sidebar } from './src/components/Sidebar/Sidebar';
import { Workspace } from './src/components/Workspace/Workspace';
import { GraphPanel } from './src/components/Graph/GraphPanel';
import {
  DatabaseIcon,
  SparklesIcon,
  GraphIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
} from './src/components/Common/Icons';
import './App.css';

export default function App() {
  // Layout collapse states
  const [isLeftSidebarCollapsed, setIsLeftSidebarCollapsed] = useState(false);
  const [isGraphPanelCollapsed, setIsGraphPanelCollapsed] = useState(false);

  // Collections & Documents state
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>('default');
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<string>('');
  const [selectedCommunity, setSelectedCommunity] = useState<string>('all');
  const [selectedTopicId, setSelectedTopicId] = useState<string | number | null>(null);

  // Graph state
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [nodeSearch, setNodeSearch] = useState('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // Uploading state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatusMessage, setUploadStatusMessage] = useState('');

  // Q&A state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  // Responsive mobile navigation tab
  const [activeMobileTab, setActiveMobileTab] = useState<'sidebar' | 'workspace' | 'graph'>('workspace');

  // Load collections & documents summary
  const refreshSummary = useCallback(async (preferredColId?: string) => {
    try {
      const summary = await api.getSummary();
      setCollections(summary.collections);
      setDocuments(summary.documents);

      const targetColId =
        preferredColId ||
        (summary.collections.some((c) => c.collection_id === selectedCollectionId)
          ? selectedCollectionId
          : summary.collections[0]?.collection_id || 'default');

      setSelectedCollectionId(targetColId);
      return targetColId;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not load summary.';
      setGraphError(msg);
      return selectedCollectionId;
    }
  }, [selectedCollectionId]);

  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  // Load graph for selected collection / document / community
  useEffect(() => {
    if (!selectedCollectionId) return;

    let cancelled = false;
    setIsLoadingGraph(true);
    setGraphError(null);

    const commId = selectedTopicId !== null ? selectedTopicId : selectedCommunity;

    api
      .getGraph({
        collectionId: selectedCollectionId,
        documentName: selectedDocument || undefined,
        communityId: commId !== 'all' ? commId : undefined,
      })
      .then((data) => {
        if (!cancelled) {
          setGraph(data);
          setIsLoadingGraph(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setGraphError(err instanceof Error ? err.message : 'Could not load knowledge graph.');
          setIsLoadingGraph(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCollectionId, selectedDocument, selectedCommunity, selectedTopicId]);

  // Handle Collection Creation
  async function handleCreateCollection(name: string, description?: string) {
    try {
      const created = await api.createCollection(name, description);
      await refreshSummary(created.id);
      setSelectedDocument('');
      setSelectedTopicId(null);
      setSelectedNode(null);
      setSelectedEdge(null);
      setMessages([]);
      setAskResult(null);
    } catch (err) {
      throw err;
    }
  }

  // Handle Multi-Document Upload
  async function handleUploadDocuments(files: File[]) {
    if (files.length === 0 || isUploading) return;
    setIsUploading(true);
    setUploadStatusMessage(`Preparing to upload ${files.length} document(s)...`);

    const activeCol = collections.find((c) => c.collection_id === selectedCollectionId);
    const colName = activeCol?.name || selectedCollectionId;
    let successCount = 0;
    const errors: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUploadStatusMessage(`Uploading (${i + 1}/${files.length}): "${file.name}"...`);
      try {
        await api.uploadDocument(file, selectedCollectionId, colName);
        successCount++;
      } catch (err) {
        errors.push(`${file.name}: ${err instanceof Error ? err.message : 'Upload failed'}`);
      }
    }

    if (errors.length > 0) {
      setUploadStatusMessage(
        `Uploaded ${successCount}/${files.length} file(s). Errors: ${errors.join('; ')}`
      );
    } else {
      setUploadStatusMessage(
        `All ${successCount} document(s) processed and added to "${colName}".`
      );
    }

    setIsUploading(false);
    await refreshSummary(selectedCollectionId);
  }

  // Handle Question Submission
  async function handleAskQuestion(submittedQuestion: string) {
    const trimmed = submittedQuestion.trim();
    if (!trimmed || isAsking) return;

    setApiError(null);
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsAsking(true);
    setAskResult(null);

    try {
      const res = await api.ask(trimmed, selectedCollectionId || undefined);
      setAskResult(res);

      const pathData: GraphData = {
        nodes: res.path?.nodes ?? [],
        edges: res.path?.edges ?? [],
      };

      const evidenceList =
        res.evidence && res.evidence.length > 0
          ? res.evidence
          : (pathData.edges
              .filter((e) => e.evidence)
              .map((e) => ({
                document_name: e.documentName || e.document_names?.[0],
                documentName: e.documentName || e.document_names?.[0],
                passage_id: e.passageId || e.passage_ids?.[0],
                passageId: e.passageId || e.passage_ids?.[0],
                page: e.page,
                text: e.evidence,
                evidence: e.evidence,
                confidence: e.confidence,
              })) as typeof res.evidence);

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: res.answer,
        timestamp: new Date(),
        evidence: evidenceList,
        answerPath: pathData,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'The question could not be answered.';
      setApiError(msg);
      const errorMsg: ChatMessage = {
        id: `assistant-error-${Date.now()}`,
        role: 'assistant',
        content: msg,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsAsking(false);
    }
  }

  // Derive dynamic topic groups from actual graph nodes and communities
  const topicGroups = useMemo<TopicGroup[]>(() => {
    if (!graph || graph.nodes.length === 0) return [];

    const degrees = new Map<string, number>();
    for (const edge of graph.edges) {
      degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
      degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
    }

    const groupsMap = new Map<
      number | string,
      { nodeIds: string[]; topNodeLabel: string; maxDegree: number }
    >();

    for (const node of graph.nodes) {
      if (node.type === 'Document' || node.type === 'Passage') continue;
      const commId =
        node.community_id !== undefined && node.community_id >= 0
          ? node.community_id
          : 'general';

      if (!groupsMap.has(commId)) {
        groupsMap.set(commId, {
          nodeIds: [],
          topNodeLabel: node.label,
          maxDegree: degrees.get(node.id) ?? 0,
        });
      }
      const group = groupsMap.get(commId)!;
      group.nodeIds.push(node.id);
      const deg = degrees.get(node.id) ?? 0;
      if (deg > group.maxDegree) {
        group.maxDegree = deg;
        group.topNodeLabel = node.label;
      }
    }

    const result: TopicGroup[] = [];
    for (const [id, data] of groupsMap.entries()) {
      const label =
        id === 'general'
          ? `Topic: ${data.topNodeLabel}`
          : `Group ${Number(id) + 1}: ${data.topNodeLabel}`;
      result.push({
        id,
        label,
        nodeCount: data.nodeIds.length,
        nodeIds: data.nodeIds,
      });
    }

    return result.sort((a, b) => b.nodeCount - a.nodeCount);
  }, [graph]);

  // Derive salient key terms from concept nodes in active graph sorted by connectivity
  const keyTerms = useMemo<KeyTerm[]>(() => {
    if (!graph || graph.nodes.length === 0) return [];

    const degrees = new Map<string, number>();
    for (const edge of graph.edges) {
      degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
      degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
    }

    const conceptNodes = graph.nodes.filter(
      (n) => n.type !== 'Document' && n.type !== 'Passage'
    );

    return conceptNodes
      .map((n) => ({
        id: n.id,
        label: n.label,
        degree: degrees.get(n.id) ?? 0,
        type: n.entity_type || n.type,
        community_id: n.community_id,
      }))
      .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label))
      .slice(0, 16);
  }, [graph]);

  // Calculate live graph statistics strictly from returned data
  const graphStats = useMemo<GraphStats>(() => {
    if (!graph || graph.nodes.length === 0) {
      return {
        totalNodes: 0,
        totalEdges: 0,
        communitiesCount: 0,
        disconnectedComponents: 0,
        isolatedConcepts: 0,
      };
    }

    const conceptNodes = graph.nodes.filter(
      (n) => n.type !== 'Document' && n.type !== 'Passage'
    );
    const adjacency = new Map<string, Set<string>>();
    for (const n of conceptNodes) adjacency.set(n.id, new Set());
    for (const e of graph.edges) {
      if (adjacency.has(e.source) && adjacency.has(e.target)) {
        adjacency.get(e.source)?.add(e.target);
        adjacency.get(e.target)?.add(e.source);
      }
    }

    const visited = new Set<string>();
    let components = 0;
    for (const n of conceptNodes) {
      if (visited.has(n.id)) continue;
      components++;
      const stack = [n.id];
      while (stack.length > 0) {
        const cur = stack.pop();
        if (!cur || visited.has(cur)) continue;
        visited.add(cur);
        for (const neighbor of adjacency.get(cur) ?? []) {
          if (!visited.has(neighbor)) stack.push(neighbor);
        }
      }
    }

    const isolatedConcepts = conceptNodes.filter(
      (n) => (adjacency.get(n.id)?.size ?? 0) === 0
    ).length;
    const communitiesSet = new Set<number>();
    for (const n of graph.nodes) {
      if (n.community_id !== undefined && n.community_id >= 0) {
        communitiesSet.add(n.community_id);
      }
    }

    return {
      totalNodes: graph.nodes.length,
      totalEdges: graph.edges.length,
      communitiesCount: communitiesSet.size,
      disconnectedComponents: Math.max(components, 1),
      isolatedConcepts,
    };
  }, [graph]);

  // Combined visible graph filtered by topic or search
  const visibleGraph = useMemo(() => {
    if (!graph && !askResult) return null;
    const graphNodes = graph?.nodes ?? [];
    const graphEdges = graph?.edges ?? [];
    const pathNodes = askResult?.path.nodes ?? [];
    const pathEdges = askResult?.path.edges ?? [];

    const highlightedNodeIds = new Set(pathNodes.map((n) => n.id));
    const highlightedEdgeKeys = new Set(pathEdges.map(edgeKey));

    const includeIds = new Set<string>(highlightedNodeIds);
    if (selectedNode) includeIds.add(selectedNode.id);

    const search = nodeSearch.trim().toLowerCase();

    for (const n of graphNodes) {
      let matches = true;

      // Filter by selected topic group
      if (selectedTopicId !== null && selectedTopicId !== 'all') {
        if (selectedTopicId === 'general') {
          if (n.community_id !== undefined && n.community_id >= 0) matches = false;
        } else if (String(n.community_id) !== String(selectedTopicId)) {
          matches = false;
        }
      }

      // Filter by search term
      if (search && !n.label.toLowerCase().includes(search)) {
        matches = false;
      }

      if (matches) {
        includeIds.add(n.id);
      }
    }

    const nodes = [...graphNodes, ...pathNodes].filter(
      (n, idx, arr) =>
        includeIds.has(n.id) && arr.findIndex((x) => x.id === n.id) === idx
    );
    const nodeIdsSet = new Set(nodes.map((n) => n.id));

    const allEdges = [...graphEdges, ...pathEdges];
    const edgesMap = new Map<string, GraphEdge>();
    for (const e of allEdges) {
      if (nodeIdsSet.has(e.source) && nodeIdsSet.has(e.target)) {
        edgesMap.set(edgeKey(e), e);
      }
    }

    return {
      nodes,
      edges: Array.from(edgesMap.values()),
      highlightedNodeIds,
      highlightedEdgeKeys,
    };
  }, [graph, askResult, selectedTopicId, nodeSearch, selectedNode]);

  // Available communities in current graph for toolbar
  const availableCommunities = useMemo(() => {
    const set = new Set<number>();
    (graph?.nodes ?? []).forEach((n) => {
      if (n.community_id !== undefined && n.community_id >= 0) set.add(n.community_id);
    });
    return Array.from(set).sort((a, b) => a - b);
  }, [graph]);

  const activeCollection = collections.find((c) => c.collection_id === selectedCollectionId);

  return (
    <div className="app-root-layout">
      {/* Mobile Top Navigation Tabs */}
      <nav className="mobile-tabs-bar" aria-label="Mobile Navigation">
        <button
          type="button"
          className={`mobile-tab-btn ${activeMobileTab === 'sidebar' ? 'active' : ''}`}
          onClick={() => setActiveMobileTab('sidebar')}
        >
          <DatabaseIcon size={16} />
          <span>Collections</span>
        </button>
        <button
          type="button"
          className={`mobile-tab-btn ${activeMobileTab === 'workspace' ? 'active' : ''}`}
          onClick={() => setActiveMobileTab('workspace')}
        >
          <SparklesIcon size={16} />
          <span>Q&A</span>
        </button>
        <button
          type="button"
          className={`mobile-tab-btn ${activeMobileTab === 'graph' ? 'active' : ''}`}
          onClick={() => setActiveMobileTab('graph')}
        >
          <GraphIcon size={16} />
          <span>Graph</span>
        </button>
      </nav>

      {/* Main 3-Column Desktop Layout */}
      <div
        className={`main-columns-grid tab-${activeMobileTab} ${
          isLeftSidebarCollapsed ? 'sidebar-collapsed' : ''
        } ${isGraphPanelCollapsed ? 'graph-collapsed' : ''}`}
      >
        {/* Floating edge toggle for Left Sidebar when collapsed */}
        {isLeftSidebarCollapsed && (
          <button
            type="button"
            className="floating-rail-toggle left-rail-toggle"
            onClick={() => setIsLeftSidebarCollapsed(false)}
            title="Show left sidebar"
            aria-label="Show left sidebar"
          >
            <ChevronRightIcon size={15} />
          </button>
        )}

        {/* LEFT COLUMN: Sidebar */}
        <div className={`column-sidebar-wrap ${isLeftSidebarCollapsed ? 'collapsed' : ''}`}>
          <Sidebar
            collections={collections}
            selectedCollectionId={selectedCollectionId}
            onSelectCollection={(id) => {
              setSelectedCollectionId(id);
              setSelectedDocument('');
              setSelectedTopicId(null);
              setSelectedNode(null);
              setSelectedEdge(null);
              setMessages([]);
              setAskResult(null);
              setActiveMobileTab('workspace');
            }}
            onCreateCollection={handleCreateCollection}
            documents={documents}
            selectedDocument={selectedDocument}
            onSelectDocument={(doc) => setSelectedDocument(doc)}
            onUploadDocuments={handleUploadDocuments}
            isUploading={isUploading}
            uploadStatusMessage={uploadStatusMessage}
            topicGroups={topicGroups}
            selectedTopicId={selectedTopicId}
            onSelectTopic={(topicId) => setSelectedTopicId(topicId)}
            keyTerms={keyTerms}
            selectedTermId={selectedNode?.id ?? null}
            onSelectTerm={(term) => {
              const node = graph?.nodes.find((n) => n.id === term.id);
              if (node) {
                setSelectedNode(node);
                setIsGraphPanelCollapsed(false);
                setActiveMobileTab('graph');
              }
            }}
            isCollapsed={isLeftSidebarCollapsed}
            onToggleCollapse={() => setIsLeftSidebarCollapsed((prev) => !prev)}
          />
        </div>

        {/* CENTER COLUMN: Question-Answer Workspace */}
        <div
          className={`column-workspace-wrap ${
            isGraphPanelCollapsed ? 'graph-collapsed' : ''
          } ${isLeftSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
        >
          <Workspace
            activeCollection={activeCollection}
            messages={messages}
            isAsking={isAsking}
            onAsk={handleAskQuestion}
            selectedNode={selectedNode}
            onClearSelectedNode={() => setSelectedNode(null)}
            onSelectNode={(node) => {
              setSelectedNode(node);
              if (node) {
                setIsGraphPanelCollapsed(false);
                setActiveMobileTab('graph');
              }
            }}
            onSelectEdge={(edge) => {
              setSelectedEdge(edge);
              if (edge) {
                setIsGraphPanelCollapsed(false);
                setActiveMobileTab('graph');
              }
            }}
            apiError={apiError}
            isLeftSidebarCollapsed={isLeftSidebarCollapsed}
            onToggleLeftSidebar={() => setIsLeftSidebarCollapsed((prev) => !prev)}
            isGraphPanelCollapsed={isGraphPanelCollapsed}
            onToggleGraphPanel={() => setIsGraphPanelCollapsed((prev) => !prev)}
          />
        </div>

        {/* Floating edge toggle for Right Knowledge Graph panel when collapsed */}
        {isGraphPanelCollapsed && (
          <button
            type="button"
            className="floating-rail-toggle right-rail-toggle"
            onClick={() => setIsGraphPanelCollapsed(false)}
            title="Show Knowledge Graph"
            aria-label="Show Knowledge Graph"
          >
            <ChevronLeftIcon size={15} />
          </button>
        )}

        {/* RIGHT COLUMN: Interactive Knowledge Graph */}
        <div className={`column-graph-wrap ${isGraphPanelCollapsed ? 'collapsed' : ''}`}>
          <GraphPanel
            graph={visibleGraph}
            graphStats={graphStats}
            isLoading={isLoadingGraph}
            graphError={graphError}
            activeCollection={activeCollection}
            collectionDocs={documents.filter(
              (d) => !d.collection_id || d.collection_id === selectedCollectionId
            )}
            selectedDocument={selectedDocument}
            onSelectDocument={(doc) => setSelectedDocument(doc)}
            selectedCommunity={selectedCommunity}
            onSelectCommunity={(comm) => setSelectedCommunity(comm)}
            availableCommunities={availableCommunities}
            nodeSearch={nodeSearch}
            onNodeSearchChange={(val) => setNodeSearch(val)}
            highlightedNodeIds={visibleGraph?.highlightedNodeIds ?? new Set()}
            highlightedEdgeKeys={visibleGraph?.highlightedEdgeKeys ?? new Set()}
            selectedNode={selectedNode}
            onSelectNode={(node) => setSelectedNode(node)}
            selectedEdge={selectedEdge}
            onSelectEdge={(edge) => setSelectedEdge(edge)}
            onAskAboutNode={(node) => {
              setSelectedNode(node);
              setActiveMobileTab('workspace');
            }}
            isCollapsed={isGraphPanelCollapsed}
            onToggleCollapse={() => setIsGraphPanelCollapsed((prev) => !prev)}
          />
        </div>
      </div>
    </div>
  );
}
