import { AskResponse, CollectionSummary, DocumentSummary, GraphData } from '../types/graph';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function readJson(response: Response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export const api = {
  async getSummary(): Promise<{ collections: CollectionSummary[]; documents: DocumentSummary[] }> {
    const res = await fetch(`${API_BASE_URL}/api/graph/summary`);
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? 'Failed to retrieve collections and documents summary.');
    }
    return {
      collections: (data.collections ?? []) as CollectionSummary[],
      documents: (data.documents ?? []) as DocumentSummary[],
    };
  },

  async getCollections(): Promise<CollectionSummary[]> {
    const res = await fetch(`${API_BASE_URL}/api/graph/collections`);
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? 'Failed to retrieve collections list.');
    }
    return (data.collections ?? []) as CollectionSummary[];
  },

  async createCollection(name: string, description?: string, collectionId?: string): Promise<{ id: string; name: string }> {
    const res = await fetch(`${API_BASE_URL}/api/graph/collections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        description: description?.trim() || undefined,
        collection_id: collectionId?.trim() || undefined,
      }),
    });
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? 'Failed to create collection.');
    }
    const id = data.id || data.collection_id || name.toLowerCase().trim().replace(/\s+/g, '_');
    return { id, name: data.name ?? name };
  },

  async uploadDocument(
    file: File,
    collectionId: string,
    collectionName?: string,
    startPage?: number,
    endPage?: number
  ): Promise<{ message: string; document_name: string }> {
    const formData = new FormData();
    formData.append('file', file);
    if (collectionId) formData.append('collection_id', collectionId);
    if (collectionName) formData.append('collection_name', collectionName);
    if (startPage !== undefined) formData.append('start_page', String(startPage));
    if (endPage !== undefined) formData.append('end_page', String(endPage));

    const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
      method: 'POST',
      body: formData,
    });
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? `Failed to upload "${file.name}".`);
    }
    return {
      message: data.message ?? `"${file.name}" uploaded and processed successfully.`,
      document_name: data.document_name ?? file.name,
    };
  },

  async getGraph(params: {
    collectionId?: string;
    documentName?: string;
    communityId?: string | number;
  }): Promise<GraphData> {
    const query = new URLSearchParams();
    if (params.collectionId) query.set('collection_id', params.collectionId);
    if (params.documentName) query.set('document_name', params.documentName);
    if (params.communityId !== undefined && params.communityId !== 'all') {
      query.set('community_id', String(params.communityId));
    }

    const url = `${API_BASE_URL}/api/graph/graph${query.toString() ? `?${query.toString()}` : ''}`;
    const res = await fetch(url);
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? 'Failed to load graph data.');
    }
    return {
      nodes: data.nodes ?? [],
      edges: data.edges ?? [],
    };
  },

  async ask(question: string, collectionId?: string): Promise<AskResponse> {
    const res = await fetch(`${API_BASE_URL}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: question.trim(),
        collection_id: collectionId || undefined,
      }),
    });
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.detail ?? 'Failed to answer question.');
    }
    return {
      answer: data.answer ?? '',
      path: {
        nodes: data.path?.nodes ?? [],
        edges: data.path?.edges ?? [],
      },
      evidence: data.evidence ?? [],
      nodes: data.nodes ?? [],
      communities: data.communities ?? [],
    };
  },
};
