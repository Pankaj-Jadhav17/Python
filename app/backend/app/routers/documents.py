import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from pypdf.errors import LimitReachedError

from app.services.pdf_graph_service import PDFGraphService

router = APIRouter()
service = PDFGraphService()


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        content = await file.read()
        temp_file.write(content)
        temp_file.close()

        try:
            text = service.extract_text_from_pdf(temp_file.name)
        except LimitReachedError as error:
            raise HTTPException(
                status_code=413,
                detail="This PDF contains a compressed stream larger than the 250 MB processing limit.",
            ) from error
        if not text.strip():
            raise HTTPException(status_code=400, detail="No readable text found in the PDF.")

        result = service.create_graph(file.filename, text)
        return {
            "message": "PDF ingested and graph generated successfully.",
            **result,
        }
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
