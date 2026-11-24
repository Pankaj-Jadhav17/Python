import React, { useEffect, useRef } from 'react';
import ForceGraph3D, { ForceGraph3DInstance } from '3d-force-graph';
import { GraphData, GraphNode, GraphEdge } from '../../types/graph';
import { GraphIcon } from '../Common/Icons';

type RelatedSubgraphProps = {
  path: GraphData;
  onSelectNode?: (node: GraphNode | null) => void;
  onSelectEdge?: (edge: GraphEdge | null) => void;
};

export const RelatedSubgraph: React.FC<RelatedSubgraphProps> = ({
  path,
  onSelectNode,
  onSelectEdge,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraph3DInstance | null>(null);

  const hasContent = path.nodes.length > 0 && path.edges.length > 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !hasContent) return;

    const graph = new ForceGraph3D(el)
      .backgroundColor('#070a12')
      .width(el.clientWidth)
      .height(200)
      .nodeRelSize(4.5)
      .nodeColor(() => '#a855f7') // Electric purple for answer path
      .nodeLabel((n) => (n as GraphNode).label)
      .linkColor(() => '#38bdf8') // Electric cyan for path links
      .linkWidth(2.2)
      .linkDirectionalParticles(2)
      .linkDirectionalParticleWidth(2.5)
      .linkDirectionalParticleColor(() => '#38bdf8')
      .linkDirectionalArrowLength(3.5)
      .linkDirectionalArrowRelPos(1)
      .linkLabel((l: any) => l.edge?.evidence ? `${l.edge.label}: ${l.edge.evidence}` : l.edge?.label ?? '')
      .onNodeClick((n) => onSelectNode?.(n as GraphNode))
      .onLinkClick((l: any) => onSelectEdge?.(l.edge as GraphEdge))
      .onBackgroundClick(() => {
        onSelectNode?.(null);
        onSelectEdge?.(null);
      });

    const links = path.edges.map((e) => ({
      source: e.source,
      target: e.target,
      edge: e,
    }));

    graph.graphData({
      nodes: path.nodes.map((n) => ({ ...n })),
      links,
    });

    graphRef.current = graph;

    const timer = setTimeout(() => {
      graph.zoomToFit(500, 30);
    }, 400);

    const observer = new ResizeObserver(() => {
      graph.width(el.clientWidth);
    });
    observer.observe(el);

    return () => {
      clearTimeout(timer);
      observer.disconnect();
      graph._destructor();
      el.replaceChildren();
      graphRef.current = null;
    };
  }, [path, hasContent, onSelectNode, onSelectEdge]);

  if (!hasContent) {
    return (
      <div className="subgraph-empty-state">
        <GraphIcon size={16} className="subgraph-empty-icon" />
        <span>No connected graph path was found for this answer.</span>
      </div>
    );
  }

  return (
    <div className="related-subgraph-card">
      <div className="subgraph-card-header">
        <div className="subgraph-title-row">
          <GraphIcon size={14} className="subgraph-icon" />
          <h4>Related Subgraph</h4>
        </div>
        <span className="subgraph-stats-badge">
          {path.nodes.length} concept{path.nodes.length === 1 ? '' : 's'} · {path.edges.length} connection{path.edges.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="subgraph-canvas-container" ref={containerRef} />
    </div>
  );
};
