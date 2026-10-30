from sentence_transformers import CrossEncoder


class Reranker:

    def __init__(
        self,
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"
    ):

        print("Loading reranker model...")

        self.model = CrossEncoder(
            model_name
        )

    def rerank(
        self,
        query,
        documents,
        top_k=8
    ):

        if not documents:
            return []

        pairs = [
            (
                query,
                document.page_content
            )
            for document in documents
        ]

        scores = self.model.predict(
            pairs
        )

        ranked_documents = sorted(
            zip(
                documents,
                scores
            ),
            key=lambda item: item[1],
            reverse=True
        )

        # -----------------------------------------------------
        # Debug ranking scores
        # -----------------------------------------------------

        print("\nRERANKING SCORES")
        print("-" * 70)

        for i, (document, score) in enumerate(
            ranked_documents[:top_k]
        ):

            section = document.metadata.get(
                "section",
                "General"
            )

            page_start = document.metadata.get(
                "page_start",
                "?"
            )

            page_end = document.metadata.get(
                "page_end",
                page_start
            )

            print(
                f"[{i + 1}] "
                f"Score: {float(score):.4f} | "
                f"Pages: {page_start}-{page_end} | "
                f"Section: {section}"
            )

        # -----------------------------------------------------
        # Return top documents
        # -----------------------------------------------------

        return [
            document
            for document, score
            in ranked_documents[:top_k]
        ]