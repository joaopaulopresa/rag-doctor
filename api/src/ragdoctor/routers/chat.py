"""The public side: status, chat and the source documents behind citations."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

import ragbench as rb
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ragdoctor import models
from ragdoctor.auth import Db, chat_access
from ragdoctor.catalog import describe
from ragdoctor.db import session_factory
from ragdoctor.routers.deps import RagDep
from ragdoctor.services import chat
from ragdoctor.services.indexing import index_exists
from ragdoctor.services.questions import from_feedback
from ragdoctor.state import active_activation, live_collection, spec_of

router = APIRouter(prefix="/api", tags=["chat"])
Visitor = Annotated[models.User | None, Depends(chat_access)]


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Feedback(BaseModel):
    value: Literal[1, -1]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
async def library_status(db: Db, rag: RagDep) -> dict[str, object]:
    activation = await active_activation(db)
    collection = await live_collection(db)
    documents = await db.scalar(
        select(func.count()).select_from(models.Document).where(models.Document.status == "ready")
    )
    pending = await db.scalar(
        select(func.count()).select_from(models.Document).where(models.Document.status == "pending")
    )
    questions = await db.scalar(
        select(func.count())
        .select_from(models.Question)
        .where(models.Question.status == "accepted")
    )
    configuration = None
    ready = False
    if activation is not None:
        spec = spec_of(activation.configuration)
        configuration = {"name": activation.configuration.name, **describe(spec)}
        ready = collection is not None and await index_exists(rag, spec, collection)
    return {
        "ready": ready,
        "documents": documents,
        "pending_documents": pending,
        "questions": questions,
        "configuration": configuration,
    }


@router.post("/chat")
async def ask(body: Ask, rag: RagDep, _: Visitor) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async with session_factory()() as db:
            try:
                async for event in chat.ask(db, rag, body.question.strip()):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except chat.ChatUnavailableError as error:
                yield f"data: {json.dumps({'type': 'error', 'message': str(error)})}\n\n"
            except rb.RagBenchError as error:
                message = f"The answer could not be produced: {error}"
                yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/{message_id}/feedback")
async def feedback(message_id: int, body: Feedback, db: Db, _: Visitor) -> dict[str, object]:
    message = await db.get(models.ChatMessage, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such message.")
    message.feedback = body.value
    queued = None
    if body.value == -1:
        queued = (await from_feedback(db, message)).id
    await db.commit()
    return {"ok": True, "review_question_id": queued}


@router.get("/documents/{document_id:path}")
async def document(document_id: str, db: Db, _: Visitor) -> dict[str, object]:
    row = await db.get(models.Document, document_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    return {"id": row.id, "title": row.title, "source": row.source, "text": row.text}
