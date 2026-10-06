from pathlib import Path

from knowledge_agent.loaders.loader import DocumentLoader

pdf_path = (
    Path(__file__).parent.parent
    / "data"
    / "documents"
    / "sample.pdf"
)

loader = DocumentLoader()

documents = loader.load_document(str(pdf_path))

print("=" * 60)
print(f"Total pages loaded: {len(documents)}")
print("=" * 60)

print("\nMetadata:\n")
print(documents[0].metadata)

print("\nFirst 500 characters:\n")
print(documents[0].page_content[:500])