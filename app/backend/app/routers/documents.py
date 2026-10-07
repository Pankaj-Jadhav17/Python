import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.services.evidence_graph_service import EvidenceGraphService

router = APIRouter()
service = EvidenceGraphService()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    start_page: int | None = None,
    end_page: int | None = None,
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file name is required.")

    extension = Path(file.filename).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF, DOCX, or TXT file.",
        )
    if extension != ".pdf" and (start_page is not None or end_page is not None):
        raise HTTPException(status_code=400, detail="Page ranges can only be used with PDF files.")
    if (start_page is not None and start_page < 1) or (end_page is not None and end_page < 1):
        raise HTTPException(status_code=400, detail="PDF page numbers must be positive.")

    temp_file = tempfile.NamedTemporaryFile(suffix=extension, delete=False)
    try:
        while content := await file.read(1024 * 1024):
            temp_file.write(content)
        temp_file.close()

        try:
            service.check_ollama()
            passages = service.iter_passages(
                temp_file.name,
                extension,
                file.filename,
                start_page,
                end_page,
            )
            result = await run_in_threadpool(service.create_evidence_graph, file.filename, passages)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "message": "Document passages and evidence graph ingested successfully.",
            **result,
        }
    finally:
        await file.close()
        temp_file.close()
        Path(temp_file.name).unlink(missing_ok=True)
