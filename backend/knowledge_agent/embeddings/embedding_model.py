from langchain_huggingface import HuggingFaceEmbeddings
import torch

MODEL_NAME = "BAAI/bge-base-en-v1.5"


def resolve_device():
    """Return the torch device to load embeddings on.

    Probed at construction rather than import time so that importing this
    module does not initialise the CUDA context.

    Returns:
        Either "cuda" or "cpu".
    """
    return "cuda" if torch.cuda.is_available() else "cpu"


class EmbeddingModel:

    def __init__(self, model_name=MODEL_NAME, device=None):
        self.device = device or resolve_device()
        self.embedding_model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": self.device},
            encode_kwargs={"normalize_embeddings": True},
        )

    def get_model(self):
        return self.embedding_model