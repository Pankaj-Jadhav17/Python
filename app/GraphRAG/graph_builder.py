from collections import OrderedDict

from app.config import config


def build_graph_data(triples: list[dict], *, max_nodes: int | None = None, max_edges: int | None = None) -> dict:
    max_nodes = max_nodes or config.max_graph_nodes
    max_edges = max_edges or config.max_graph_edges
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str, str]] = set()

    ordered_nodes: OrderedDict[str, dict] = OrderedDict()
    for triple in triples:
        subject = str(triple.get("subject", "")).strip()
        relation = str(triple.get("relation", "")).strip()
        objective = str(triple.get("object", "")).strip()
        if not subject or not objective or not relation:
            continue
        for name, type_name in ((subject, "Concept"), (objective, "Concept")):
            if name and name not in seen_nodes:
                ordered_nodes[name] = {"id": f"concept:{name}", "label": name, "type": type_name}
                seen_nodes.add(name)
        edge_key = (subject, objective, relation, str(triple.get("passage_id") or ""))
        if edge_key not in seen_edges:
            edges.append({
                "source": f"concept:{subject}",
                "target": f"concept:{objective}",
                "label": relation,
                "evidence": triple.get("evidence"),
                "passageId": triple.get("passage_id"),
                "page": triple.get("page"),
                "confidence": triple.get("confidence"),
                "status": triple.get("status", "verified"),
                "documentName": triple.get("document_name"),
            })
            seen_edges.add(edge_key)

    nodes = list(ordered_nodes.values())
    if len(nodes) > max_nodes:
        nodes = nodes[:max_nodes]
    if len(edges) > max_edges:
        edges = edges[:max_edges]
    return {"nodes": nodes, "edges": edges}
