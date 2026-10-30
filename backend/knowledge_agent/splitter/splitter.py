import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class DocumentSplitter:

    def __init__(
        self,
        chunk_size=2000,
        chunk_overlap=400
    ):

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    # =========================================================
    # HEADING DETECTION
    # =========================================================

    def _is_heading(self, line):

        cleaned = line.strip()

        if not cleaned:
            return False

        # Ignore page markers
        if re.match(
            r"^\[PAGE\s+\d+\]$",
            cleaned,
            re.IGNORECASE
        ):
            return False

        # -----------------------------------------------------
        # Numbered headings
        # -----------------------------------------------------

        if re.match(
            r"^\d+(?:\.\d+)*[\.\)]?\s+.{2,120}$",
            cleaned
        ):
            return True

        # -----------------------------------------------------
        # Lettered headings
        # -----------------------------------------------------

        if re.match(
            r"^[A-Z][\.\)]\s+.{2,120}$",
            cleaned
        ):
            return True

        # -----------------------------------------------------
        # Roman numeral headings
        # -----------------------------------------------------

        if re.match(
            r"^[IVXLCDM]+[\.\)]\s+.{2,120}$",
            cleaned,
            re.IGNORECASE
        ):
            return True

        # -----------------------------------------------------
        # ALL CAPS headings
        # -----------------------------------------------------

        if (
            len(cleaned) <= 100
            and cleaned.upper() == cleaned
            and any(
                character.isalpha()
                for character in cleaned
            )
            and not cleaned.endswith(".")
        ):
            return True

        return False

    # =========================================================
    # HEADING EXTRACTION
    # =========================================================

    def _extract_heading(self, line):

        cleaned = line.strip()

        if self._is_heading(cleaned):
            return cleaned

        return None

    # =========================================================
    # TABLE OF CONTENTS DETECTION
    # =========================================================

    def _is_table_of_contents(self, text):

        if not text:
            return False

        text_lower = text.lower()

        # -----------------------------------------------------
        # Strong indicator
        #
        # Only treat a page as TOC when the page itself
        # contains an explicit TOC/Contents heading.
        # -----------------------------------------------------

        if (
            "table of contents" in text_lower
            or re.search(
                r"(^|\n)\s*contents\s*($|\n)",
                text_lower
            )
        ):
            return True

        # -----------------------------------------------------
        # Dotted TOC entries
        #
        # Require several entries AND a significant amount
        # of dotted structure.
        # -----------------------------------------------------

        dotted_entries = re.findall(
            r"\.{5,}\s*[A-Za-z0-9IVXLCDM]+",
            text,
            re.IGNORECASE
        )

        if len(dotted_entries) >= 6:
            return True

        return False

    # =========================================================
    # CREATE NORMAL CHUNK
    # =========================================================

    def _create_chunk(
        self,
        text,
        source,
        section,
        pages
    ):

        text = text.strip()

        if not text:
            return None

        # -----------------------------------------------------
        # Remove page markers when checking whether this is
        # only a heading.
        # -----------------------------------------------------

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
            and not re.match(
                r"^\[PAGE\s+\d+\]$",
                line,
                re.IGNORECASE
            )
        ]

        # -----------------------------------------------------
        # Ignore heading-only chunks
        # -----------------------------------------------------

        if len(lines) <= 1:

            if (
                lines
                and self._is_heading(
                    lines[0]
                )
            ):
                return None

        # -----------------------------------------------------
        # Clean page list
        # -----------------------------------------------------

        valid_pages = [
            page
            for page in pages
            if page is not None
        ]

        # -----------------------------------------------------
        # Chroma does not accept an empty list.
        #
        # If somehow no page metadata survived, try to recover
        # the page number from the text itself.
        # -----------------------------------------------------

        if not valid_pages:

            page_matches = re.findall(
                r"\[PAGE\s+(\d+)\]",
                text,
                re.IGNORECASE
            )

            valid_pages = [
                int(page)
                for page in page_matches
            ]

        # -----------------------------------------------------
        # If there is STILL no page number, don't store an
        # empty list in Chroma.
        # -----------------------------------------------------

        metadata = {
            "source": source,
            "section": section,
        }

        if valid_pages:

            metadata.update(
                {
                    "page_start": min(
                        valid_pages
                    ),
                    "page_end": max(
                        valid_pages
                    ),
                    "pages": sorted(
                        set(valid_pages)
                    ),
                }
            )

        else:

            metadata.update(
                {
                    "page_start": None,
                    "page_end": None,
                    "pages": [0],
                }
            )

        return Document(
            page_content=text,
            metadata=metadata
        )

    # =========================================================
    # SPLIT LARGE SECTION
    # =========================================================

    def _split_large_section(
        self,
        text,
        source,
        section,
        pages
    ):

        temporary_document = Document(
            page_content=text,
            metadata={
                "source": source,
                "section": section,
            }
        )

        sub_chunks = self.splitter.split_documents(
            [temporary_document]
        )

        results = []

        for chunk in sub_chunks:

            # -------------------------------------------------
            # Extract page numbers from the chunk
            # -------------------------------------------------

            page_numbers = []

            for match in re.finditer(
                r"\[PAGE\s+(\d+)\]",
                chunk.page_content,
                re.IGNORECASE
            ):

                page_numbers.append(
                    int(match.group(1))
                )

            # -------------------------------------------------
            # Fall back to section pages
            # -------------------------------------------------

            if not page_numbers:

                page_numbers = [
                    page
                    for page in pages
                    if page is not None
                ]

            # -------------------------------------------------
            # Ignore heading-only chunks
            # -------------------------------------------------

            cleaned_lines = [
                line.strip()
                for line in chunk.page_content.splitlines()
                if line.strip()
                and not re.match(
                    r"^\[PAGE\s+\d+\]$",
                    line,
                    re.IGNORECASE
                )
            ]

            if (
                len(cleaned_lines) <= 1
                and cleaned_lines
                and self._is_heading(
                    cleaned_lines[0]
                )
            ):
                continue

            # -------------------------------------------------
            # Make sure page list is never empty
            # -------------------------------------------------

            if not page_numbers:

                page_numbers = [0]

            chunk.metadata.update(
                {
                    "source": source,
                    "section": section,
                    "page_start": min(
                        page_numbers
                    ),
                    "page_end": max(
                        page_numbers
                    ),
                    "pages": sorted(
                        set(page_numbers)
                    ),
                }
            )

            results.append(
                chunk
            )

        return results

    # =========================================================
    # MAIN SPLIT FUNCTION
    # =========================================================

    def split(self, documents):

        if not documents:
            return []

        chunks = []

        source = documents[0].metadata.get(
            "source",
            ""
        )

        current_section = "General"

        current_section_text = []

        current_section_pages = []

        # =====================================================
        # PROCESS EACH PAGE
        # =====================================================

        for document in documents:

            page = document.metadata.get(
                "page",
                None
            )

            # PyMuPDF uses zero-based page numbers.
            if page is not None:
                page = page + 1

            page_text = document.page_content.strip()

            if not page_text:
                continue

            # -------------------------------------------------
            # Skip genuine TOC pages
            # -------------------------------------------------

            if self._is_table_of_contents(
                page_text
            ):

                print(
                    f"Skipping likely Table of Contents "
                    f"page: {page}"
                )

                continue

            page_marker = f"[PAGE {page}]"

            lines = page_text.splitlines()

            # -------------------------------------------------
            # Make sure the page marker is added before the
            # page's actual content.
            # -------------------------------------------------

            current_section_text.append(
                page_marker
            )

            if page is not None:

                if page not in current_section_pages:

                    current_section_pages.append(
                        page
                    )

            # =================================================
            # PROCESS LINES
            # =================================================

            for line in lines:

                heading = self._extract_heading(
                    line
                )

                # =================================================
                # NEW SECTION
                # =================================================

                if heading:

                    # -------------------------------------------------
                    # Save previous section
                    # -------------------------------------------------

                    if current_section_text:

                        complete_section = "\n".join(
                            current_section_text
                        ).strip()

                        if complete_section:

                            if (
                                len(complete_section)
                                <= self.chunk_size
                            ):

                                chunk = self._create_chunk(
                                    complete_section,
                                    source,
                                    current_section,
                                    current_section_pages
                                )

                                if chunk is not None:

                                    chunks.append(
                                        chunk
                                    )

                            else:

                                chunks.extend(
                                    self._split_large_section(
                                        complete_section,
                                        source,
                                        current_section,
                                        current_section_pages
                                    )
                                )

                    # -------------------------------------------------
                    # Start new section
                    # -------------------------------------------------

                    current_section = heading

                    current_section_text = [
                        page_marker,
                        heading
                    ]

                    current_section_pages = []

                    if page is not None:

                        current_section_pages.append(
                            page
                        )

                    continue

                # =================================================
                # NORMAL CONTENT
                # =================================================

                current_section_text.append(
                    line
                )

        # =====================================================
        # SAVE FINAL SECTION
        # =====================================================

        if current_section_text:

            complete_section = "\n".join(
                current_section_text
            ).strip()

            if complete_section:

                if (
                    len(complete_section)
                    <= self.chunk_size
                ):

                    chunk = self._create_chunk(
                        complete_section,
                        source,
                        current_section,
                        current_section_pages
                    )

                    if chunk is not None:

                        chunks.append(
                            chunk
                        )

                else:

                    chunks.extend(
                        self._split_large_section(
                            complete_section,
                            source,
                            current_section,
                            current_section_pages
                        )
                    )

        # =====================================================
        # FINAL CLEANUP
        # =====================================================

        chunks = [
            chunk
            for chunk in chunks
            if chunk.page_content.strip()
        ]

        return chunks