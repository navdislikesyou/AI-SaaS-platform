"""Service layer for the Knowledge Agent.

Wraps :class:`knowledge_agent.knowledge_agent.KnowledgeAgent` in a dict-in,
dict-out interface so the API never has to know the agent's call shapes.
The agent returns a bare integer from ``ingest`` and a tuple from ``ask``;
both are translated here.

Loading the embedding model, the vector store, and the LLM happens once in
:meth:`KnowledgeService.__init__`, never per call.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from knowledge_agent.knowledge_agent import KnowledgeAgent
from knowledge_agent.llm.local_llm import LocalLLM

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Dict-in, dict-out facade over the Knowledge Agent.

    The service owns no retrieval logic of its own. It translates between the
    agent's native return shapes and the dictionaries the API layer expects.
    """

    def __init__(self, settings: Settings) -> None:
        """Load the embedding model, vector store, and LLM once.

        Args:
            settings: Application settings supplying the Chroma directory,
                the embedding model name, and the Ollama connection details.

        Raises:
            Exception: Whatever the embedding model, Chroma, or Ollama client
                raises at construction. Construction is deliberately eager so
                that a missing model surfaces here rather than on first use.
        """
        self._settings = settings

        self._agent = KnowledgeAgent(
            chroma_path=settings.resolved_knowledge_chroma_path,
            embedding_model=settings.knowledge_embedding_model,
            llm=LocalLLM(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
            ),
        )

        logger.info(
            "knowledge_service_ready model=%s chroma_path=%s",
            settings.ollama_model,
            settings.resolved_knowledge_chroma_path,
        )

    def ingest(
        self,
        file_path: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Index a document into the knowledge base.

        Args:
            file_path: Path to a PDF, DOCX, or TXT file.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal. The
                organization is written onto every indexed chunk so the
                retrieval path can scope queries to it.

        Returns:
            A dictionary with ``indexed`` reporting whether any chunk was
            stored, and ``chunk_count`` holding the number of chunks written.

        Raises:
            ValueError: If the file extension is not supported by the loader.
        """
        chunk_count = int(self._agent.ingest(file_path, user_context=user_context) or 0)

        logger.info(
            "knowledge_ingest indexed_chunks=%d source=%s",
            chunk_count,
            file_path,
        )

        return {
            "indexed": chunk_count > 0,
            "chunk_count": chunk_count,
        }

    def query(
        self,
        question: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Answer a question from the indexed documents.

        Args:
            question: The natural language question to answer.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal. The
                organization scopes retrieval, so another organization's
                documents cannot reach the prompt or the citations.

        Returns:
            A dictionary with ``answer`` holding the generated text and
            ``sources`` holding the deduplicated ``{"source", "page"}``
            citations the answer was drawn from.
        """
        answer, sources = self._agent.ask(question, user_context=user_context)

        logger.info("knowledge_query source_count=%d", len(sources))

        return {
            "answer": answer,
            "sources": sources,
        }
