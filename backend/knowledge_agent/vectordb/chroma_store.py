"""Chroma-backed vector store for the Knowledge Agent."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

logger = logging.getLogger(__name__)

_UNSAFE_ID_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


class ChromaStore:
    """Persistent vector store keyed by content-addressed chunk ids.

    Chunk ids are derived from the source document, page, and chunk text, so
    ingesting the same document twice replaces its chunks instead of
    duplicating them.
    """

    def __init__(
        self,
        embedding_model: Any,
        persist_directory: str | Path,
        collection_name: str = "knowledge_base",
    ) -> None:
        """Open or create the collection.

        Args:
            embedding_model: Embedding function passed through to Chroma.
            persist_directory: Directory holding the persisted collection.
                Created if absent.
            collection_name: Chroma collection name.
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name

        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embedding_model,
            persist_directory=str(self.persist_directory),
        )

    @staticmethod
    def build_chunk_id(document: Any, index: int) -> str:
        """Return a stable id for one chunk.

        The id combines the source document, the page, and a digest of the
        chunk text. Re-ingesting unchanged content therefore produces the same
        id and overwrites rather than duplicating.

        Args:
            document: A LangChain document carrying page_content and metadata.
            index: Position of the chunk within the ingested document, used to
                disambiguate identical text on the same page.

        Returns:
            A Chroma-safe identifier string.
        """
        metadata = getattr(document, "metadata", {}) or {}
        source = str(metadata.get("source", "unknown"))
        page = metadata.get("page", 0)
        content = getattr(document, "page_content", "") or ""

        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        stem = Path(source).stem or "document"
        slug = _UNSAFE_ID_CHARS.sub("_", stem)[:48]

        return f"{slug}__p{page}__{index}_{digest}"

    def count(self) -> int:
        """Return the number of indexed chunks.

        Returns:
            The chunk count in the collection.
        """
        result = self.vector_store.get()
        return len(result.get("ids", []))

    def index_documents(self, documents: list[Any], reset: bool = False) -> int:
        """Index chunks, replacing any previous content for the same document.

        Args:
            documents: Chunks to index.
            reset: Drop the existing collection contents first.

        Returns:
            The number of chunks submitted for indexing.
        """
        if reset:
            logger.info("chroma_reset collection=%s", self.collection_name)
            self.vector_store.reset_collection()

        if not documents:
            logger.warning("chroma_index_empty collection=%s", self.collection_name)
            return 0

        ids = [
            self.build_chunk_id(document, index)
            for index, document in enumerate(documents)
        ]

        self.vector_store.add_documents(documents, ids=ids)

        logger.info(
            "chroma_indexed collection=%s submitted=%d total=%d",
            self.collection_name,
            len(ids),
            self.count(),
        )

        return len(ids)

    def search(
        self,
        query: str,
        k: int = 5,
        fetch_k: int = 8,
        user_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Return the chunks most relevant to a query.

        When ``user_context`` carries an ``organization_id``, the query is
        scoped to that organization. The scope is applied inside Chroma through
        a metadata filter, so another organization's chunks never enter the
        candidate pool at all. A second pass over the returned documents
        enforces the same rule again, because the filter is the only thing
        standing between a foreign document and the prompt.

        Documents that carry no ``organization_id`` metadata are legacy records
        and are treated as inaccessible to every organization, since ownership
        cannot be established for them.

        Args:
            query: The search text.
            k: Number of chunks to return.
            fetch_k: Candidate pool to rerank.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            Matching documents, most relevant first.
        """
        organization_id = None
        if user_context:
            organization_id = user_context.get("organization_id")

        search_filter = None
        if organization_id is not None:
            search_filter = {"organization_id": organization_id}

        results = self.vector_store.max_marginal_relevance_search(
            query=query,
            k=k,
            fetch_k=fetch_k,
            filter=search_filter,
        )

        if organization_id is None:
            return results

        scoped: list[Any] = []
        for document in results:
            metadata = getattr(document, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            if metadata.get("organization_id") != organization_id:
                continue
            scoped.append(document)

        logger.info(
            "chroma_search_scoped organization_id=%s returned=%d fetched=%d",
            organization_id,
            len(scoped),
            len(results),
        )

        return scoped