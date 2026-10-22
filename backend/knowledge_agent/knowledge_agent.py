from knowledge_agent.embeddings.embedding_model import EmbeddingModel
from knowledge_agent.llm.local_llm import LocalLLM
from knowledge_agent.loaders.loader import DocumentLoader
from knowledge_agent.splitter.splitter import DocumentSplitter
from knowledge_agent.vectordb.chroma_store import ChromaStore


class KnowledgeAgent:

    def __init__(self, chroma_path, embedding_model=None, llm=None):

        self.loader = DocumentLoader()

        self.splitter = DocumentSplitter()

        self.embedding_model = EmbeddingModel(
            model_name=embedding_model
        ).get_model()

        self.vector_store = ChromaStore(
            self.embedding_model,
            persist_directory=chroma_path,
        )

        self.llm = llm or LocalLLM()

    def ingest(self, file_path, reset=False, user_context=None):

        documents = self.loader.load_document(file_path)

        chunks = self.splitter.split(documents)

        self._stamp_ownership(chunks, user_context)

        return self.vector_store.index_documents(chunks, reset=reset)

    def ask(self, question, user_context=None):

        # retrieve the top 4 most relevant chunks
        results = self.vector_store.search(question, k=4, user_context=user_context)

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

    def _stamp_ownership(self, chunks, user_context):
        """Write the owning organization onto every chunk about to be indexed.

        The metadata is what the retrieval path filters on, so a chunk without
        it belongs to no organization and stays invisible to everyone.

        Args:
            chunks: The chunks to stamp, modified in place.
            user_context: Optional dict with ``user_id`` and
                ``organization_id`` from the authenticated principal.
        """

        if not user_context:
            return

        organization_id = user_context.get("organization_id")
        owner_id = user_context.get("user_id")

        for chunk in chunks:
            metadata = getattr(chunk, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            metadata["organization_id"] = organization_id
            metadata["owner_id"] = owner_id