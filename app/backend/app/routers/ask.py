from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.services.question_service import service as question_service

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/ask")
async def ask_question(payload: AskRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return await run_in_threadpool(question_service.ask, payload.question)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503 if isinstance(error, RuntimeError) else 400, detail=str(error)) from error
