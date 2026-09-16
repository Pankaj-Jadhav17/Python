from __future__ import annotations

from pathlib import Path

from RAG.ingest import ingest_file, ingest_text
from RAG.retriever import query_rag


def ingest_your_text() -> None:
    # Put raw user text here for embedding
    text = """
    Write your text or document content here.
    Example: 'Our product helps users manage customer support tickets.'
    """
    rows = ingest_text(text, source="manual", metadata={"type": "user_input"})
    print(f"Inserted {len(rows)} text chunks")


def ingest_your_pdf(pdf_path: str | Path) -> None:
    # Put path to a PDF file here and it will be chunked + embedded
    rows = ingest_file(pdf_path, source="pdf")
    print(f"Inserted {len(rows)} PDF chunks from {pdf_path}")


def ask_question(question: str, top_k: int = 5) -> None:
    results = query_rag(question, top_k=top_k)
    for item in results:
        print("-" * 60)
        print(f"Score: {item['score']:.4f}")
        print(item["content"])
        print(item["metadata"])


if __name__ == "__main__":
    # 1) Example: add raw text
    ingest_your_text()

    # 2) Example: add a PDF
    # ingest_your_pdf("/absolute/path/to/your-file.pdf")

    # 3) Example: ask a question against stored embeddings
    # ask_question("What does this document say about support tickets?", top_k=3)
    pass
