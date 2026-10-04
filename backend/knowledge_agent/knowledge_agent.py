from knowledge_agent.loaders.loader import DocumentLoader
from knowledge_agent.splitter.splitter import DocumentSplitter
from knowledge_agent.embeddings.embedding_model import EmbeddingModel
from knowledge_agent.vectordb.chroma_store import ChromaStore
from knowledge_agent.llm.local_llm import LocalLLM


class KnowledgeAgent:

    def __init__(self):

        self.loader = DocumentLoader()

        self.splitter = DocumentSplitter()

        self.embedding_model = EmbeddingModel().get_model()

        self.vector_store = ChromaStore(self.embedding_model)

        self.llm = LocalLLM()

    def ingest(self, file_path):

        documents = self.loader.load_document(file_path)

        chunks = self.splitter.split(documents)

        self.vector_store.index_documents(chunks)

    def ask(self, question):

        # retrieve the top 4 most relevant chunks
        results = self.vector_store.search(question, k=4)

        # use the COMPLETE chunks
        context = "\n\n".join(
            doc.page_content
            for doc in results
        )

        prompt = f"""
You are an Enterprise Knowledge Assistant.

You MUST answer ONLY using the provided context.

Instructions:
- Read the complete context carefully.
- Combine information from multiple retrieved sections if needed.
- Do not use outside knowledge.
- Do not make assumptions.
- If the answer exists in the context, answer it clearly.
- If the answer is NOT present in the context, reply exactly:

"I could not find that information in the uploaded documents."

Context:
{context}

Question:
{question}

Answer:
"""

        answer = self.llm.generate(prompt).strip()

        sources = []

        seen = set()

        for doc in results:

            page = doc.metadata.get("page", 0) + 1
            source = doc.metadata.get("source", "")

            key = (source, page)

            if key in seen:
                continue

            seen.add(key)

            sources.append(
                {
                    "page": page,
                    "source": source,
                }
            )

        return answer, sources