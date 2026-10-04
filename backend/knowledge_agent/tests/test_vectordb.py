from pathlib import Path

from backend.knowledge_agent.loaders.loader import DocumentLoader
from backend.knowledge_agent.splitter.splitter import DocumentSplitter
from backend.knowledge_agent.embeddings.embedding_model import EmbeddingModel
from backend.knowledge_agent.vectordb.chroma_store import ChromaStore


pdf_path = (
    Path(__file__).parent.parent
    / "data"
    / "documents"
    / "sample.pdf"
)

loader = DocumentLoader()
documents = loader.load_document(str(pdf_path))

splitter = DocumentSplitter()
chunks = splitter.split(documents)

embedding_model = EmbeddingModel().get_model()

vector_store = ChromaStore(embedding_model)

vector_store.index_documents(chunks)

results = vector_store.search(
    "How many casual leaves are employees entitled to?"
)

print("=" * 60)

for i, result in enumerate(results, start=1):

    print(f"\nResult {i}\n")

    print(result.page_content[:500])

    print("\nMetadata:")

    print(result.metadata)

    print("=" * 60)