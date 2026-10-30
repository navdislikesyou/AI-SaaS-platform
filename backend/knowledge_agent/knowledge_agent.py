from backend.knowledge_agent.loaders.loader import (
    DocumentLoader
)

from backend.knowledge_agent.splitter.splitter import (
    DocumentSplitter
)

from backend.knowledge_agent.vectordb.chroma_store import (
    ChromaStore
)

from backend.knowledge_agent.retriever.reranker import (
    Reranker
)

from backend.knowledge_agent.embeddings.embedding_model import (
    EmbeddingModel
)

from backend.knowledge_agent.llm.local_llm import (
    LocalLLM
)


class KnowledgeAgent:

    def __init__(self):

        print("\nInitializing Knowledge Agent...\n")

        # =====================================================
        # DOCUMENT LOADER
        # =====================================================

        self.loader = DocumentLoader()

        # =====================================================
        # DOCUMENT SPLITTER
        # =====================================================

        self.splitter = DocumentSplitter(
            chunk_size=2000,
            chunk_overlap=400
        )

        # =====================================================
        # EMBEDDING MODEL
        # =====================================================

        print("Loading embedding model...")

        embedding_wrapper = EmbeddingModel()

        self.embedding_model = (
            embedding_wrapper.get_model()
        )

        # =====================================================
        # VECTOR DATABASE
        # =====================================================

        self.vector_store = ChromaStore(
            self.embedding_model
        )

        # =====================================================
        # RERANKER
        # =====================================================

        self.reranker = Reranker()

        # =====================================================
        # LOCAL LLM
        # =====================================================

        print("Loading local LLM...")

        self.llm = LocalLLM()

        print(
            "\nKnowledge Agent initialized successfully.\n"
        )

    # =========================================================
    # INGEST DOCUMENT
    # =========================================================

    def ingest(self, file_path):

        print("\nLoading document...\n")

        documents = self.loader.load_document(
            file_path
        )

        print(
            f"Loaded {len(documents)} document sections."
        )

        chunks = self.splitter.split(
            documents
        )

        print(
            f"Created {len(chunks)} chunks."
        )

        self.vector_store.index_documents(
            chunks
        )

    # =========================================================
    # ASK
    # =========================================================

    def ask(self, question):

        print("\n" + "=" * 70)
        print("QUESTION")
        print("=" * 70)

        print(question)

        # =====================================================
        # VECTOR SEARCH
        # =====================================================

        print(
            "\nRetrieving relevant document chunks..."
        )

        candidates = self.vector_store.search(
            query=question,
            k=15
        )

        print(
            f"Retrieved {len(candidates)} candidate chunks."
        )

        # =====================================================
        # STRUCTURAL FILTER
        # =====================================================

        print(
            "\nFiltering structural and very small chunks..."
        )

        content_candidates = []

        for document in candidates:

            content = document.page_content.strip()

            if len(content) < 150:
                continue

            content_candidates.append(
                document
            )

        print(
            f"Remaining after filtering: "
            f"{len(content_candidates)} chunks."
        )

        # =====================================================
        # RERANK
        # =====================================================

        print(
            "\nReranking retrieved chunks..."
        )

        documents = self.reranker.rerank(
            query=question,
            documents=content_candidates,
            top_k=6
        )

        print(
            f"Selected {len(documents)} chunks "
            "after reranking."
        )

        # =====================================================
        # BUILD CONTEXT
        # =====================================================

        context_parts = []

        for i, document in enumerate(
            documents
        ):

            metadata = document.metadata

            source = metadata.get(
                "source",
                "Unknown"
            )

            page_start = metadata.get(
                "page_start",
                "?"
            )

            page_end = metadata.get(
                "page_end",
                page_start
            )

            section = metadata.get(
                "section",
                "General"
            )

            context_parts.append(
                f"""
SOURCE {i + 1}

File: {source}

Pages: {page_start}-{page_end}

Section: {section}

CONTENT:

{document.page_content}
"""
            )

        context = "\n".join(
            context_parts
        )

        # =====================================================
        # RAG PROMPT
        # =====================================================

        prompt = f"""
You are a general-purpose Knowledge Assistant.

Answer the user's question using ONLY the retrieved
document context below.

The retrieved context may contain several different
sections. Some sections may be relevant to the question
while others may be unrelated.

You must determine relevance from the actual content.

============================================================
STRICT GROUNDING RULES
============================================================

1. Answer the user's question using the retrieved document
   context.

2. Treat the retrieved context as the authoritative source
   for your answer.

3. Every factual statement must be supported by the retrieved
   context.

4. Do not use general knowledge to replace information that
   is already present in the retrieved context.

5. If one retrieved source directly answers the user's
   question, use that source directly.

6. Do not reject a directly supported answer simply because
   other retrieved sources are unrelated.

7. Some retrieved sources may be irrelevant to the question.
   Ignore irrelevant sources.

8. Do not combine unrelated sources into an answer.

9. Do not infer information that is not stated or directly
   supported by the retrieved context.

10. Do not invent missing information.

11. Preserve exact numbers, dates, names, durations,
    conditions, and terminology from the document.

12. If the document explicitly provides an answer, do not
    say that the information is unavailable.

13. If the retrieved context genuinely does not contain
    enough information to answer the question, say:

    "The available document context does not contain enough
    information to answer this question."

14. Do not claim that information is missing when it is
    explicitly present in the retrieved context.

15. Do not add generic advice, recommendations, disclaimers,
    warnings, or background information that is not supported
    by the retrieved context.

16. Do not tell the user to contact HR, a supervisor,
    administrator, lawyer, doctor, or another authority unless
    the retrieved document explicitly instructs them to do so.

17. Do not use information from an unrelated section merely
    because it contains similar words.

============================================================
HOW TO HANDLE DIFFERENT QUESTIONS
============================================================

If the question asks for a specific fact:

Answer directly using the retrieved source that contains
that fact.

If the question asks for a list:

List the items explicitly provided by the retrieved source.

If the question asks for a broad topic:

Combine the relevant retrieved sections, but only include
information that is actually supported by those sections.

If the question asks about something that is not covered:

Clearly state that the available retrieved context does not
provide enough information.

============================================================
ANSWER STYLE
============================================================

- Answer the question directly.
- Prefer the most relevant retrieved source.
- Use other retrieved sources only when they add relevant
  information.
- Do not mention the retrieval process.
- Do not mention embeddings, Chroma, reranking, or the LLM.
- Do not make the answer longer simply because more context
  was retrieved.

============================================================
RETRIEVED DOCUMENT CONTEXT
============================================================

{context}

============================================================
USER QUESTION
============================================================

{question}

============================================================
ANSWER
============================================================
"""

        # =====================================================
        # GENERATE
        # =====================================================

        print(
            "\nGenerating answer...\n"
        )

        answer = self.llm.generate(
            prompt
        )

        # =====================================================
        # SOURCES
        # =====================================================

        sources = []

        for document in documents:

            metadata = document.metadata

            sources.append(
                {
                    "source": metadata.get(
                        "source",
                        "Unknown"
                    ),
                    "page_start": metadata.get(
                        "page_start",
                        "?"
                    ),
                    "page_end": metadata.get(
                        "page_end",
                        "?"
                    ),
                    "section": metadata.get(
                        "section",
                        "General"
                    )
                }
            )

        return {
            "answer": answer,
            "sources": sources
        }