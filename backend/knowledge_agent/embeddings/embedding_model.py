from langchain_huggingface import HuggingFaceEmbeddings
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"

class EmbeddingModel:

    def __init__(self):
        self.embedding_model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-base-en-v1.5",
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )

    def get_model(self):
        return self.embedding_model