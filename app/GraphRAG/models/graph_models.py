from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EntityMention:
    mention_id: str
    surface_text: str
    normalized_name: str
    entity_type: str
    passage_id: str
    document_id: str
    document_revision_id: str | None = None
    start_offset: int = 0
    end_offset: int = 0
    surrounding_context: str = ""


@dataclass(slots=True)
class CanonicalEntity:
    canonical_id: str
    canonical_name: str
    entity_type: str = "Concept"
    aliases: list[str] = field(default_factory=list)
    collection_id: str = "default"
    resolution_method: str = "exact_normalized"
    resolution_status: str = "verified"
    community_id: int | None = None


@dataclass(slots=True)
class RelationshipCandidate:
    candidate_id: str
    subject: str
    predicate: str
    object: str
    evidence: str
    passage_id: str
    document_id: str
    subject_type: str | None = None
    object_type: str | None = None
    document_name: str | None = None
    revision_id: str | None = None
    direction: str = "directed"
    polarity: str = "positive"
    modality: str = "factual"
    confidence: float = 0.8
    status: str = "pending"


@dataclass(slots=True)
class EvidenceRecord:
    evidence_id: str
    document_id: str
    document_name: str
    passage_id: str
    evidence: str
    revision_id: str | None = None
    page: int | None = None
    confidence: float = 0.8
    status: str = "verified"
    created_at: str | None = None


@dataclass(slots=True)
class CollectionRecord:
    collection_id: str
    name: str
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    document_count: int = 0
    concept_count: int = 0
    relationship_count: int = 0


@dataclass(slots=True)
class DocumentRecord:
    document_id: str
    collection_id: str
    name: str
    content_hash: str
    revision_id: str = "rev-1"
    status: str = "processed"
    created_at: str | None = None


@dataclass(slots=True)
class PassageRecord:
    passage_id: str
    document_id: str
    document_name: str
    page: int | None
    start_offset: int
    end_offset: int
    text: str
    embedding: list[float] | None = None
    collection_id: str = "default"
    chunk_index: int = 0
    content_hash: str | None = None


@dataclass(slots=True)
class GraphNode:
    id: str
    label: str
    type: str = "Concept"
    page: int | None = None
    community_id: int | None = None
    entity_type: str | None = None
    aliases: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    label: str
    evidence: str | None = None
    evidence_list: list[str] = field(default_factory=list)
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    page: int | None = None
    passage_id: str | None = None
    confidence: float | None = None
    status: str | None = None
    document_name: str | None = None
    document_names: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphResult:
    nodes: list[dict]
    edges: list[dict]
    mindmap: dict | None = None
    collection_id: str | None = None
