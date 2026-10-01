from pathlib import Path

from app.services.pdf_graph_service import PDFGraphService


def test_extract_entities_and_relationships_from_pdf_text():
    text = """
    Machine learning helps healthcare systems. 
    Deep learning is used in cancer detection. 
    Data science works with healthcare and machine learning.
    """

    service = PDFGraphService()
    entities, relationships = service.extract_entities_and_relationships(text)

    assert len(entities) >= 3
    assert any("machine learning" in entity.lower() for entity in entities)
    assert len(relationships) >= 1
