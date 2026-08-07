from langchain_chroma import Chroma


class ChromaStore:

    def __init__(self, embedding_model):
        self.vector_store = Chroma(
            collection_name="knowledge_base",
            embedding_function=embedding_model,
            persist_directory="./backend/knowledge_agent/data/chroma_db",
        )

    def index_documents(self, documents):
        self.vector_store.add_documents(documents)

    def search(self, query, k=3):
        return self.vector_store.similarity_search(query, k=k)