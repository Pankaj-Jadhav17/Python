from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.config import config
from .entity_resolution import detect_graph_communities


def build_graph_data(
    triples: list[dict[str, Any]],
    *,
    collection_id: str | None = None,
    max_nodes: int | None = None,
    max_edges: int | None = None,
    run_community_detection: bool = True,
) -> dict[str, Any]:
    """
    Build graph nodes and edges from triples, preserving multi-document provenance,
    entity typing, and computing graph communities.
    """
    max_nodes = max_nodes or config.max_graph_nodes
    max_edges = max_edges or config.max_graph_edges

    ordered_nodes: OrderedDict[str, dict[str, Any]] = OrderedDict()
    edges_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    for triple in triples:
        subject = str(triple.get("subject", "")).strip()
        relation = str(triple.get("relation", "") or triple.get("predicate", "")).strip()
        obj = str(triple.get("object", "")).strip()

        if not subject or not obj or not relation:
            continue

        subj_type = triple.get("subject_type") or "Concept"
        obj_type = triple.get("object_type") or "Concept"
        doc_name = triple.get("document_name") or ""
        evidence = triple.get("evidence") or ""
        passage_id = triple.get("passage_id") or ""
        page = triple.get("page")
        confidence = triple.get("confidence", 0.8)
        status = triple.get("status", "verified")

        subj_id = triple.get("subject_id") or f"concept:{subject}"
        obj_id = triple.get("object_id") or f"concept:{obj}"

        # Register nodes
        for node_id, name, type_name in (
            (subj_id, subject, subj_type),
            (obj_id, obj, obj_type),
        ):
            if node_id not in ordered_nodes:
                ordered_nodes[node_id] = {
                    "id": node_id,
                    "label": name,
                    "type": type_name,
                    "entity_type": type_name,
                    "documents": [doc_name] if doc_name else [],
                    "aliases": [name],
                }
            else:
                existing = ordered_nodes[node_id]
                if doc_name and doc_name not in existing["documents"]:
                    existing["documents"].append(doc_name)
                if type_name != "Concept" and existing.get("type") == "Concept":
                    existing["type"] = type_name
                    existing["entity_type"] = type_name

        # Canonical edge key based on semantic claim
        edge_key = (subj_id, obj_id, relation)

        evidence_item = {
            "evidence": evidence,
            "document_name": doc_name,
            "passage_id": passage_id,
            "page": page,
            "confidence": confidence,
            "status": status,
        }

        if edge_key not in edges_map:
            edges_map[edge_key] = {
                "source": subj_id,
                "target": obj_id,
                "label": relation,
                "evidence": evidence,
                "evidence_list": [evidence] if evidence else [],
                "evidence_records": [evidence_item] if evidence else [],
                "documentName": doc_name,
                "document_names": [doc_name] if doc_name else [],
                "passageId": passage_id,
                "passage_ids": [passage_id] if passage_id else [],
                "page": page,
                "confidence": confidence,
                "status": status,
                "collection_id": collection_id,
            }
        else:
            edge = edges_map[edge_key]
            if evidence and evidence not in edge["evidence_list"]:
                edge["evidence_list"].append(evidence)
                edge["evidence_records"].append(evidence_item)
            if doc_name and doc_name not in edge["document_names"]:
                edge["document_names"].append(doc_name)
            if passage_id and passage_id not in edge["passage_ids"]:
                edge["passage_ids"].append(passage_id)
            if confidence > edge.get("confidence", 0.0):
                edge["confidence"] = confidence

    nodes = list(ordered_nodes.values())[:max_nodes]
    valid_node_ids = {n["id"] for n in nodes}

    edges = [
        edge
        for edge in edges_map.values()
        if edge["source"] in valid_node_ids and edge["target"] in valid_node_ids
    ][:max_edges]

    # Run analytical community detection if requested
    if run_community_detection and nodes and edges:
        communities = detect_graph_communities(nodes, edges)
        for node in nodes:
            node["community_id"] = communities.get(node["id"], 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "collection_id": collection_id,
    }
