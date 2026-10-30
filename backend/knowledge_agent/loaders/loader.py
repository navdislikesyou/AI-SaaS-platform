from pathlib import Path

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    Docx2txtLoader,
)


class DocumentLoader:

    def load_document(self, file_path: str):
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            loader = PyMuPDFLoader(file_path)

        elif suffix == ".docx":
            loader = Docx2txtLoader(file_path)

        elif suffix == ".txt":
            loader = TextLoader(
                file_path,
                encoding="utf-8"
            )

        else:
            raise ValueError(
                f"Unsupported file type: {suffix}"
            )

        return loader.load()