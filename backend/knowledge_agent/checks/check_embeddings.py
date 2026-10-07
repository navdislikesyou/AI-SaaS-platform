from knowledge_agent.embeddings.embedding_model import EmbeddingModel

embedding_model = EmbeddingModel().get_model()

vector = embedding_model.embed_query(
    "What is the leave policy?"
)

print(f"Embedding Dimension : {len(vector)}")

print(vector[:10])