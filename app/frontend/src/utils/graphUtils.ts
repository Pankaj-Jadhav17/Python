import { GraphNode, GraphEdge } from '../types/graph';

export function edgeKey(edge: GraphEdge): string {
  const pId = edge.passageId ?? (edge.passage_ids?.[0] ?? '');
  return `${edge.source}|${edge.target}|${edge.label}|${pId}`;
}

const PALETTE = [
  '#8b5cf6', // purple
  '#3b82f6', // blue
  '#06b6d4', // cyan
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ec4899', // pink
  '#6366f1', // indigo
  '#14b8a6', // teal
  '#f97316', // orange
  '#a855f7', // violet
];

const COMMUNITY_COLORS = [
  '#6366f1', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b',
  '#ec4899', '#8b5cf6', '#14b8a6', '#f97316', '#64748b',
];

export function getNodeColor(node: GraphNode): string {
  if (node.type === 'Document') return '#3b82f6';
  if (node.type === 'Passage') return '#06b6d4';

  if (node.community_id !== undefined && node.community_id >= 0) {
    return COMMUNITY_COLORS[node.community_id % COMMUNITY_COLORS.length];
  }

  const typeKey = node.entity_type || node.type || 'Entity';
  let hash = 0;
  for (let i = 0; i < typeKey.length; i++) {
    hash = (hash << 5) - hash + typeKey.charCodeAt(i);
    hash |= 0;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}
