from pathlib import Path

import pytest

from GraphRAG.document_loader import extract_document_text, iter_document_chunks
from GraphRAG.extractor import extract_triples, validate_extracted_triples


def test_document_loader_reads_txt_in_overlapping_chunks(tmp_path: Path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("x" * (64 * 1024 - 10) + "Microspore develops into pollen grain.", encoding="utf-8")

    chunks = list(iter_document_chunks(str(file_path), ".txt"))

    assert chunks
    assert any("Microspore develops into pollen grain." in chunk for chunk in chunks)


def test_document_loader_extracts_pdf_and_docx_text(tmp_path: Path):
    pymupdf = pytest.importorskip("pymupdf")
    file_path = tmp_path / "chapters.pdf"
    document = pymupdf.open()
    for page_text in ("Front matter", "Microspore develops into pollen grain.", "Chapter two text"):
        page = document.new_page()
        page.insert_text((72, 72), page_text)
    document.save(file_path)
    document.close()

    pdf_chunks = list(iter_document_chunks(str(file_path), ".pdf", start_page=2, end_page=2))
    assert "Microspore develops into pollen grain." in "\n".join(pdf_chunks)

    docx = pytest.importorskip("docx")
    docx_path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("Microspore develops into pollen grain.")
    document.save(docx_path)

    assert list(iter_document_chunks(str(docx_path), ".docx")) == ["Microspore develops into pollen grain."]
    assert extract_document_text(str(docx_path), ".docx") == "Microspore develops into pollen grain."


def test_extractor_validates_relationships_from_text():
    text = "Microspore develops into pollen grain. Ovule develops into seed."
    triples = extract_triples(text)

    assert any(
        item["subject"].lower() == "microspore"
        and item["relation"] == "develops into"
        and item["object"].lower() == "pollen grain"
        for item in triples
    )

    valid = [{
        "subject": "Microspore",
        "relation": "develops into",
        "object": "pollen grain",
        "evidence": "Microspore develops into pollen grain.",
        "confidence": 0.9,
    }]
    assert validate_extracted_triples(text, valid)[0]["subject"] == "Microspore"


def test_extractor_rejects_invalid_evidence():
    text = "Microspore develops into pollen grain."
    invalid = [{
        "subject": "Microspore",
        "relation": "develops into",
        "object": "seed",
        "evidence": "Ovule develops into seed.",
        "confidence": 0.9,
    }]

    assert validate_extracted_triples(text, invalid) == []
