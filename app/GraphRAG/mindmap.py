def prepare_mindmap(graph_data: dict | None, *, max_depth: int = 3) -> dict:
    graph = graph_data or {"nodes": [], "edges": []}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    nodes_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    root_nodes = [node for node in nodes if node.get("type") in {"Document", "Concept"}][:5]
    nested = []
    for node in root_nodes:
        children = [
            {
                "id": edge.get("target"),
                "label": nodes_by_id.get(edge.get("target"), {}).get("label", edge.get("target")),
                "type": nodes_by_id.get(edge.get("target"), {}).get("type", "Concept"),
            }
            for edge in edges
            if edge.get("source") == node.get("id")
        ][:max_depth]
        nested.append({
            "id": node.get("id"),
            "label": node.get("label"),
            "type": node.get("type"),
            "children": children,
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "mindmap": {"nodes": nested, "type": "mindmap"},
    }
