from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from GraphRAG.retriever import answer_question

router = APIRouter()

# Backwards-compatible service hook used by the existing tests and older app code.
question_service = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/ask")
async def ask_question(payload: AskRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        if question_service is not None:
            return await run_in_threadpool(question_service.ask, payload.question)
        return await run_in_threadpool(answer_question, payload.question)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503 if isinstance(error, RuntimeError) else 400, detail=str(error)) from error
