def compute_layout(nodes: list) -> list:
    # stub: compute 3D positions for nodes
    for i, n in enumerate(nodes):
        n.setdefault("x", i)
        n.setdefault("y", 0)
        n.setdefault("z", 0)
    return nodes
