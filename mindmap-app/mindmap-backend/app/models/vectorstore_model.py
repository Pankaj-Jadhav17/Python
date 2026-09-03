class VectorStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def upsert(self, vectors: list):
        pass

    def query(self, vector, top_k=10):
        return []
