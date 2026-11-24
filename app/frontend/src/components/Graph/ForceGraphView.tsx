import React, { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import ForceGraph3D, { ForceGraph3DInstance } from '3d-force-graph';
import { GraphNode, GraphEdge } from '../../types/graph';
import { edgeKey, getNodeColor } from '../../utils/graphUtils';

export { edgeKey, getNodeColor };

export type ForceGraphViewHandle = {
  resetCamera: () => void;
  focusNode: (node: GraphNode) => void;
};

type ForceGraphViewProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodeIds: Set<string>;
  highlightedEdgeKeys: Set<string>;
  selectedNodeId: string | null;
  selectedEdgeKey: string | null;
  onNodeSelect: (node: GraphNode | null) => void;
  onEdgeSelect: (edge: GraphEdge | null) => void;
};

type ViewLink = {
  source: string;
  target: string;
  key: string;
  edge: GraphEdge;
};

export const ForceGraphView = forwardRef<ForceGraphViewHandle, ForceGraphViewProps>(({
  nodes,
  edges,
  highlightedNodeIds,
  highlightedEdgeKeys,
  selectedNodeId,
  selectedEdgeKey,
  onNodeSelect,
  onEdgeSelect,
}, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraph3DInstance | null>(null);

  const onNodeSelectRef = useRef(onNodeSelect);
  const onEdgeSelectRef = useRef(onEdgeSelect);
  onNodeSelectRef.current = onNodeSelect;
  onEdgeSelectRef.current = onEdgeSelect;

  useImperativeHandle(ref, () => ({
    resetCamera: () => {
      const graph = graphRef.current;
      if (graph) {
        graph.zoomToFit(600, 40);
      }
    },
    focusNode: (node: GraphNode) => {
      const graph = graphRef.current;
      const n = node as GraphNode & { x?: number; y?: number; z?: number };
      if (graph && n.x !== undefined && n.y !== undefined && n.z !== undefined) {
        const distance = 140;
        const ratio = 1 + distance / Math.hypot(n.x, n.y, n.z);
        graph.cameraPosition(
          { x: n.x * ratio, y: n.y * ratio, z: n.z * ratio },
          n as { x: number; y: number; z: number },
          800
        );
      }
    },
  }));

  // Initialize 3D Graph
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const graph = new ForceGraph3D(el)
      .backgroundColor('#080c14')
      .width(el.clientWidth)
      .height(el.clientHeight)
      .nodeRelSize(5)
      .nodeLabel((n) => {
        const node = n as GraphNode;
        const eType = node.entity_type && node.entity_type !== 'Concept' ? ` [${node.entity_type}]` : '';
        const comm = node.community_id !== undefined && node.community_id >= 0 ? ` (Topic ${node.community_id + 1})` : '';
        return `<div class="graph-tooltip"><strong>${node.label}</strong><small>${node.type}${eType}${comm}</small></div>`;
      })
      .linkLabel((l) => {
        const link = l as ViewLink;
        const quote = link.edge.evidence ? `<br/><span style="opacity:0.75; font-size:10px;">${link.edge.evidence.slice(0, 80)}...</span>` : '';
        return `<div class="graph-tooltip"><strong>${link.edge.label}</strong>${quote}</div>`;
      })
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .onNodeClick((n) => {
        const node = n as GraphNode & { x?: number; y?: number; z?: number };
        if (node.x !== undefined && node.y !== undefined && node.z !== undefined) {
          const distance = 130;
          const ratio = 1 + distance / Math.hypot(node.x, node.y, node.z);
          graph.cameraPosition(
            { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
            node as { x: number; y: number; z: number },
            700
          );
        }
        onNodeSelectRef.current(node);
      })
      .onLinkClick((l) => {
        onEdgeSelectRef.current((l as ViewLink).edge);
      })
      .onBackgroundClick(() => {
        onNodeSelectRef.current(null);
        onEdgeSelectRef.current(null);
      });

    graphRef.current = graph;

    const observer = new ResizeObserver(() => {
      if (el) {
        graph.width(el.clientWidth).height(el.clientHeight);
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      graph._destructor();
      el.replaceChildren();
      graphRef.current = null;
    };
  }, []);

  // Update Data
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    const links: ViewLink[] = edges
      .filter((e) => e.status !== 'rejected')
      .map((e) => ({
        source: e.source,
        target: e.target,
        key: edgeKey(e),
        edge: e,
      }));

    graph.graphData({
      nodes: nodes.map((node) => ({ ...node })),
      links,
    });
  }, [nodes, edges]);

  // Styling & Highlighting
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    const hasPath = highlightedNodeIds.size > 0;

    graph
      .nodeColor((n) => {
        const node = n as GraphNode;
        if (selectedNodeId && node.id === selectedNodeId) {
          return '#f59e0b'; // Amber focus
        }
        if (highlightedNodeIds.has(node.id)) {
          return '#c084fc'; // Vibrant electric purple for answer path
        }
        return getNodeColor(node);
      })
      .nodeOpacity(hasPath ? 0.95 : 0.88)
      .linkColor((l) => {
        const link = l as ViewLink;
        if (selectedEdgeKey && link.key === selectedEdgeKey) {
          return '#f59e0b';
        }
        if (highlightedEdgeKeys.has(link.key)) {
          return '#38bdf8'; // Electric cyan for path links
        }
        return '#334155'; // Dark subtle slate
      })
      .linkWidth((l) => {
        const link = l as ViewLink;
        if (highlightedEdgeKeys.has(link.key) || selectedEdgeKey === link.key) {
          return 3.2;
        }
        return 0.7;
      })
      .linkDirectionalParticles((l) => {
        const link = l as ViewLink;
        return highlightedEdgeKeys.has(link.key) ? 3 : 0;
      })
      .linkDirectionalParticleWidth(3)
      .linkDirectionalParticleColor(() => '#38bdf8');

    if (hasPath) {
      const timer = setTimeout(() => {
        graph.zoomToFit(700, 60, (n) => highlightedNodeIds.has((n as GraphNode).id));
      }, 700);
      return () => clearTimeout(timer);
    }
  }, [highlightedNodeIds, highlightedEdgeKeys, selectedNodeId, selectedEdgeKey, nodes, edges]);

  return <div className="force-graph-3d-canvas" ref={containerRef} aria-label="Interactive 3D knowledge graph" />;
});
