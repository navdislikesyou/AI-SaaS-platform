from pathlib import Path

from knowledge_agent.loaders.loader import DocumentLoader
from knowledge_agent.splitter.splitter import DocumentSplitter


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

print("=" * 60)
print(f"Total Chunks : {len(chunks)}")
print("=" * 60)

print("\nChunk Metadata\n")
print(chunks[0].metadata)

print("\nFirst Chunk\n")
print(chunks[0].page_content)

print("\nSecond Chunk\n")
print(chunks[1].page_content)