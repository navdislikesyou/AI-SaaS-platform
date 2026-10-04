from langchain_chroma import Chroma


class ChromaStore:

    def __init__(self, embedding_model):

        self.vector_store = Chroma(
            collection_name="knowledge_base",
            embedding_function=embedding_model,
            persist_directory="./backend/knowledge_agent/data/chroma_db",
        )

    def index_documents(self, documents):

        if self.vector_store._collection.count() > 0:

            print("Existing knowledge base found.\n")

            return

        print("Creating knowledge base for the first time...\n")

        self.vector_store.add_documents(documents)

        print("Knowledge base created successfully.\n")

    def search(self, query, k=5):

        return self.vector_store.max_marginal_relevance_search(
            query=query,
            k=k,
            fetch_k=8,
        )