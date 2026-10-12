from dataclasses import dataclass, field
from typing import Any


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


@dataclass(slots=True)
class GraphNode:
    id: str
    label: str
    type: str = "Concept"
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    label: str
    evidence: str | None = None
    page: int | None = None
    passage_id: str | None = None
    confidence: float | None = None
    status: str | None = None
    document_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphResult:
    nodes: list[dict]
    edges: list[dict]
    mindmap: dict | None = None
