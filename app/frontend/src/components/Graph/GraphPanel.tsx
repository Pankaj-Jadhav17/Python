import React, { useRef, useMemo } from 'react';
import { GraphData, GraphNode, GraphEdge, GraphStats, DocumentSummary, CollectionSummary } from '../../types/graph';
import { ForceGraphView, ForceGraphViewHandle, edgeKey, getNodeColor } from './ForceGraphView';
import { NodeDetailDrawer } from './NodeDetailDrawer';
import { EdgeDetailDrawer } from './EdgeDetailDrawer';
import {
  GraphIcon,
  SearchIcon,
  MaximizeIcon,
  AlertCircleIcon,
  PanelRightCloseIcon,
  ChevronRightIcon,
} from '../Common/Icons';

type GraphPanelProps = {
  graph: GraphData | null;
  graphStats: GraphStats;
  isLoading: boolean;
  graphError: string | null;
  activeCollection: CollectionSummary | undefined;
  collectionDocs: DocumentSummary[];
  selectedDocument: string;
  onSelectDocument: (docName: string) => void;
  selectedCommunity: string;
  onSelectCommunity: (commId: string) => void;
  availableCommunities: number[];
  nodeSearch: string;
  onNodeSearchChange: (search: string) => void;
  highlightedNodeIds: Set<string>;
  highlightedEdgeKeys: Set<string>;
  selectedNode: GraphNode | null;
  onSelectNode: (node: GraphNode | null) => void;
  selectedEdge: GraphEdge | null;
  onSelectEdge: (edge: GraphEdge | null) => void;
  onAskAboutNode: (node: GraphNode) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
};

export const GraphPanel: React.FC<GraphPanelProps> = ({
  graph,
  graphStats,
  isLoading,
  graphError,
  activeCollection,
  collectionDocs,
  selectedDocument,
  onSelectDocument,
  selectedCommunity,
  onSelectCommunity,
  availableCommunities,
  nodeSearch,
  onNodeSearchChange,
  highlightedNodeIds,
  highlightedEdgeKeys,
  selectedNode,
  onSelectNode,
  selectedEdge,
  onSelectEdge,
  onAskAboutNode,
  isCollapsed,
  onToggleCollapse,
}) => {
  const graphRef = useRef<ForceGraphViewHandle>(null);

  const hasNodes = graph && graph.nodes.length > 0;

  // Compute node map for edge inspection labels
  const nodeLabelById = useMemo(() => {
    const map = new Map<string, string>();
    if (graph) {
      for (const n of graph.nodes) {
        map.set(n.id, n.label);
      }
    }
    return map;
  }, [graph]);

  // Extract unique entity types present in this specific graph
  const presentEntityTypes = useMemo(() => {
    if (!graph || graph.nodes.length === 0) return [];
    const set = new Set<string>();
    for (const n of graph.nodes) {
      const type = n.entity_type || n.type || 'Entity';
      if (type) set.add(type);
    }
    return Array.from(set).sort();
  }, [graph]);

  const selectedEdgeKey = selectedEdge ? edgeKey(selectedEdge) : null;

  return (
    <section className="graph-panel-container" aria-label="Knowledge Graph Explorer">
      {/* Graph Panel Header */}
      <header className="graph-panel-header">
        <div className="graph-header-title-row">
          <div className="graph-title-group">
            <GraphIcon size={16} className="graph-title-icon" />
            <h2 className="graph-panel-title">Knowledge Graph</h2>
          </div>

          {activeCollection && (
            <span className="graph-collection-pill">
              {activeCollection.name}
            </span>
          )}
        </div>

        {/* Live Statistics & Collapse Action */}
        <div className="graph-header-actions-row">
          <div className="graph-stats-pills-row" aria-label="Graph Statistics">
            <div className="stat-pill">
              <strong className="stat-number">{graphStats.totalNodes}</strong>
              <span className="stat-label">nodes</span>
            </div>
            <div className="stat-pill">
              <strong className="stat-number">{graphStats.totalEdges}</strong>
              <span className="stat-label">connections</span>
            </div>
            {graphStats.communitiesCount > 0 && (
              <div className="stat-pill">
                <strong className="stat-number">{graphStats.communitiesCount}</strong>
                <span className="stat-label">communities</span>
              </div>
            )}
            <div className="stat-pill">
              <strong className="stat-number">{graphStats.disconnectedComponents}</strong>
              <span className="stat-label">components</span>
            </div>
          </div>

          {onToggleCollapse && (
            <button
              type="button"
              className="graph-panel-collapse-btn"
              onClick={onToggleCollapse}
              title="Collapse Knowledge Graph panel (expand workspace)"
              aria-label="Collapse Knowledge Graph panel"
            >
              <PanelRightCloseIcon size={16} />
            </button>
          )}
        </div>
      </header>

      {/* Filter and Control Toolbar */}
      <div className="graph-controls-toolbar">
        {/* Node search */}
        <div className="search-input-wrap">
          <SearchIcon size={13} className="search-icon" />
          <input
            type="text"
            className="graph-search-input"
            placeholder="Search concepts in graph..."
            value={nodeSearch}
            onChange={(e) => onNodeSearchChange(e.target.value)}
          />
        </div>

        {/* Document scope selector */}
        {collectionDocs.length > 1 && (
          <div className="filter-select-wrap">
            <select
              className="toolbar-select"
              value={selectedDocument}
              onChange={(e) => onSelectDocument(e.target.value)}
              title="Filter graph to specific document"
            >
              <option value="">All Documents ({collectionDocs.length})</option>
              {collectionDocs.map((doc) => (
                <option key={doc.document_name} value={doc.document_name}>
                  {doc.document_name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Topic community selector */}
        {availableCommunities.length > 1 && (
          <div className="filter-select-wrap">
            <select
              className="toolbar-select"
              value={selectedCommunity}
              onChange={(e) => onSelectCommunity(e.target.value)}
              title="Filter by topic community"
            >
              <option value="all">All Topic Groups ({availableCommunities.length})</option>
              {availableCommunities.map((cid) => (
                <option key={cid} value={String(cid)}>
                  Group {cid + 1}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Fit camera button */}
        <button
          type="button"
          className="toolbar-action-btn"
          onClick={() => graphRef.current?.resetCamera()}
          title="Reset camera and fit all nodes"
        >
          <MaximizeIcon size={14} />
          <span>Fit Graph</span>
        </button>
      </div>

      {/* Error message */}
      {graphError && (
        <div className="graph-error-banner" role="alert">
          <AlertCircleIcon size={15} />
          <span>{graphError}</span>
        </div>
      )}

      {/* Main 3D Graph Canvas & Empty/Loading States */}
      <div className="graph-canvas-viewport">
        {isLoading ? (
          <div className="canvas-state-overlay">
            <span className="spinner-lg" />
            <h3>Preparing your knowledge graph...</h3>
            <p>Constructing multi-document canonical entity mesh and connections.</p>
          </div>
        ) : !activeCollection ? (
          <div className="canvas-state-overlay">
            <GraphIcon size={40} className="empty-canvas-icon" />
            <h3>Create or select a collection to get started.</h3>
            <p>Select a collection from the sidebar to visualize its knowledge graph.</p>
          </div>
        ) : !hasNodes ? (
          <div className="canvas-state-overlay">
            <GraphIcon size={40} className="empty-canvas-icon" />
            <h3>Upload PDFs to build your knowledge graph.</h3>
            <p>Documents added to &ldquo;{activeCollection.name}&rdquo; will be processed into interactive concept networks.</p>
          </div>
        ) : (
          <>
            <ForceGraphView
              ref={graphRef}
              nodes={graph.nodes}
              edges={graph.edges}
              highlightedNodeIds={highlightedNodeIds}
              highlightedEdgeKeys={highlightedEdgeKeys}
              selectedNodeId={selectedNode?.id ?? null}
              selectedEdgeKey={selectedEdgeKey}
              onNodeSelect={onSelectNode}
              onEdgeSelect={onSelectEdge}
            />

            <div className="canvas-hint-tag">
              Drag to rotate · Scroll to zoom · Click node to inspect · Click link for evidence
            </div>
          </>
        )}

        {/* Node Detail Drawer Overlay */}
        {selectedNode && (
          <NodeDetailDrawer
            node={selectedNode}
            onClose={() => onSelectNode(null)}
            onAskAboutNode={onAskAboutNode}
          />
        )}

        {/* Edge Detail Drawer Overlay */}
        {selectedEdge && (
          <EdgeDetailDrawer
            edge={selectedEdge}
            sourceLabel={nodeLabelById.get(selectedEdge.source) ?? selectedEdge.source}
            targetLabel={nodeLabelById.get(selectedEdge.target) ?? selectedEdge.target}
            onClose={() => onSelectEdge(null)}
          />
        )}
      </div>

      {/* Dynamic Graph Legend based strictly on actual nodes */}
      {hasNodes && (
        <footer className="graph-legend-bar" aria-label="Graph Legend">
          <span className="legend-title">Legend:</span>
          {presentEntityTypes.map((type) => {
            const color = getNodeColor({ id: '', label: '', type });
            return (
              <span key={type} className="legend-item">
                <span className="legend-dot" style={{ backgroundColor: color }} />
                <span className="legend-name">{type}</span>
              </span>
            );
          })}
          {highlightedNodeIds.size > 0 && (
            <span className="legend-item path-item">
              <span className="legend-dot" style={{ backgroundColor: '#c084fc' }} />
              <span className="legend-name">Answer Path</span>
            </span>
          )}
        </footer>
      )}
    </section>
  );
};
