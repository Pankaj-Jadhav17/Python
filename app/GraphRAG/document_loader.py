from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def iter_document_chunks(
    file_path: str,
    extension: str,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> Iterable[str]:
    """Yield text chunks from supported document types without duplicating the reader logic."""
    normalized_extension = (extension or Path(file_path).suffix.lower()).lower()

    if normalized_extension == ".pdf":
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - dependency validation is exercised in runtime envs.
            raise ValueError("PyMuPDF is required to read PDF files.") from exc

        with pymupdf.open(file_path) as document:
            if document.needs_pass:
                raise ValueError("This PDF is password-protected. Remove its password and upload it again.")
            first_page = start_page or 1
            last_page = end_page or document.page_count
            if first_page > document.page_count or last_page > document.page_count:
                raise ValueError(f"This PDF has {document.page_count} pages; the requested range is out of bounds.")
            if first_page > last_page:
                raise ValueError("The starting page must be less than or equal to the ending page.")
            for page_number in range(first_page - 1, last_page):
                text = document.load_page(page_number).get_text("text", sort=True)
                if text.strip():
                    yield text
        return

    if normalized_extension == ".docx":
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - dependency validation is exercised in runtime envs.
            raise ValueError("python-docx is required to read DOCX files.") from exc

        document = Document(file_path)
        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                yield paragraph.text
        return

    if normalized_extension == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as text_file:
            carry = ""
            while chunk := text_file.read(64 * 1024):
                combined = carry + chunk
                yield combined
                carry = combined[-512:]
        return

    raise ValueError(f"Unsupported document type: {normalized_extension}")


def extract_document_text(file_path: str, extension: str, *, start_page: int | None = None, end_page: int | None = None) -> str:
    return "\n".join(iter_document_chunks(file_path, extension, start_page=start_page, end_page=end_page)).strip()
