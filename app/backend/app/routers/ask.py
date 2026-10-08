from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.routers.graph import service as graph_service
from app.services.graph_question_service import GraphQuestionService

router = APIRouter()
question_service = GraphQuestionService(graph_service.driver)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/ask")
async def ask_question(payload: AskRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return await run_in_threadpool(question_service.ask, payload.question)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
