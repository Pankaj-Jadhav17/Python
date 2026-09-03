class GraphModel:
    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri

    def create_node(self, node: dict):
        pass

    def create_relationship(self, a_id: str, b_id: str, rel_type: str):
        pass

    def get_graph(self):
        return {"nodes": [], "edges": []}
