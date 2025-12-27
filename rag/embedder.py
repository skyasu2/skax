from utils.llm import get_embeddings

class Embedder:
    def __init__(self):
        self.embeddings = get_embeddings()

    def embed_query(self, text: str):
        return self.embeddings.embed_query(text)

    def embed_documents(self, texts: list[str]):
        return self.embeddings.embed_documents(texts)
