from pydantic import BaseModel
from typing import List, Optional


class Chunk(BaseModel):
    id: str
    text: str


class Node(BaseModel):
    id: str
    label: str
    properties: Optional[dict] = None


class Edge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
