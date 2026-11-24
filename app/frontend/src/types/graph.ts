export type EvidenceRecord = {
  document_name?: string;
  passage_id?: string;
  page?: number;
  evidence?: string;
  confidence?: number;
  status?: string;
};

export type EvidenceItem = {
  passage_id?: string;
  passageId?: string;
  episode_id?: string;
  document_name?: string;
  documentName?: string;
  document_id?: string;
  collection_id?: string;
  page?: number;
  text?: string;
  evidence?: string;
  chunk_index?: number;
  score?: number;
  confidence?: number;
};

export type GraphNode = {
  id: string;
  label: string;
  type: string;
  entity_type?: string;
  community_id?: number;
  aliases?: string[];
  documents?: string[];
  page?: number;
  collection_id?: string;
  x?: number;
  y?: number;
  z?: number;
};

export type GraphEdge = {
  id?: string;
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

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type AskResponse = {
  answer: string;
  path: GraphData;
  evidence?: EvidenceItem[];
  nodes?: GraphNode[];
  communities?: any[];
};

export type CollectionSummary = {
  collection_id: string;
  name: string;
  description?: string;
  document_count: number;
  concept_count: number;
  relationship_count: number;
};

export type DocumentSummary = {
  document_name: string;
  collection_id?: string;
  passage_count: number;
  concept_count: number;
  relationship_count: number;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  evidence?: EvidenceItem[];
  answerPath?: GraphData;
};

export type GraphStats = {
  totalNodes: number;
  totalEdges: number;
  communitiesCount: number;
  disconnectedComponents: number;
  isolatedConcepts: number;
};

export type TopicGroup = {
  id: number | string;
  label: string;
  nodeCount: number;
  nodeIds: string[];
};

export type KeyTerm = {
  id: string;
  label: string;
  degree: number;
  type?: string;
  community_id?: number;
};
