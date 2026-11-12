"""Admin: documents and the question set."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ragdoctor import models
from ragdoctor.auth import Admin, Db
from ragdoctor.jobs.queue import enqueue, job_view
from ragdoctor.services.documents import add_document
from ragdoctor.services.questions import (
    dumps,
    export_file,
    import_file,
    locate_evidence,
    question_view,
)

router = APIRouter(prefix="/api/admin", tags=["library"])


@router.get("/documents")
async def documents(db: Db, _: Admin) -> dict[str, object]:
    rows = await db.execute(
        select(
            models.Document.id,
            models.Document.title,
            models.Document.source,
            models.Document.origin,
            models.Document.status,
            models.Document.error,
            models.Document.created_at,
            func.length(models.Document.text).label("characters"),
        ).order_by(models.Document.created_at.desc(), models.Document.id)
    )
    counts = dict(
        (
            await db.execute(
                select(models.Question.document_id, func.count())
                .where(models.Question.status == "accepted")
                .group_by(models.Question.document_id)
            )
        ).all()
    )
    return {"documents": [{**row._asdict(), "questions": counts.get(row.id, 0)} for row in rows]}


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload(files: list[UploadFile], db: Db, _: Admin) -> dict[str, object]:
    added, errors = [], []
    for file in files:
        try:
            document = await add_document(db, file.filename or "document.txt", await file.read())
            added.append(document.id)
        except ValueError as error:
            errors.append({"file": file.filename, "error": str(error)})
    job = None
    if added:
        job = await enqueue(db, "index", {}, title=f"Index {len(added)} new document(s)")
    await db.commit()
    return {"added": added, "errors": errors, "job": job_view(job)}


@router.delete("/documents/{document_id:path}")
async def remove(document_id: str, db: Db, _: Admin) -> dict[str, object]:
    row = await db.get(models.Document, document_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    await db.delete(row)
    job = await enqueue(db, "index", {}, title="Re-index after removing a document")
    await db.commit()
    return {"ok": True, "job": job_view(job)}


class QuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=2000)
    status: Literal["draft", "accepted", "rejected"] | None = None
    document_id: str | None = None
    evidence: str | None = Field(default=None, max_length=20000)
    note: str | None = Field(default=None, max_length=2000)


@router.get("/questions")
async def questions(
    db: Db,
    _: Admin,
    status_filter: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, object]:
    statement = select(models.Question)
    if status_filter:
        statement = statement.where(models.Question.status == status_filter)
    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(models.Question.text.ilike(pattern), models.Question.id.ilike(pattern))
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await db.scalars(
            statement.order_by(
                (models.Question.status != "draft"), models.Question.updated_at.desc()
            )
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 200))
        )
    ).all()
    documents = {
        d.id: d
        for d in (
            await db.scalars(
                select(models.Document).where(
                    models.Document.id.in_({r.document_id for r in rows if r.document_id})
                )
            )
        ).all()
    }
    tallies = dict(
        (
            await db.execute(
                select(models.Question.status, func.count()).group_by(models.Question.status)
            )
        ).all()
    )
    return {
        "total": total,
        "counts": tallies,
        "questions": [question_view(r, documents.get(r.document_id or "")) for r in rows],
    }


@router.patch("/questions/{question_id}")
async def update_question(
    question_id: str, body: QuestionUpdate, db: Db, _: Admin
) -> dict[str, object]:
    row = await db.get(models.Question, question_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.")
    if body.document_id is not None:
        row.document_id = body.document_id
    document = await db.get(models.Document, row.document_id) if row.document_id else None
    if row.document_id and document is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No such document.")
    if body.evidence is not None:
        if document is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the document first.")
        try:
            row.spans = [locate_evidence(document.text, body.evidence)]
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        row.source = document.source
    if body.text is not None:
        row.text = body.text.strip()
    if body.note is not None:
        row.note = body.note
    if body.status is not None:
        if body.status == "accepted" and (document is None or not row.spans):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A question needs a document and its gold evidence before it can be accepted.",
            )
        row.status = body.status
    await db.commit()
    await db.refresh(row)
    return {"question": question_view(row, document)}


class DraftRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    seed: int = 0


@router.post("/questions/draft")
async def draft(body: DraftRequest, db: Db, _: Admin) -> dict[str, object]:
    job = await enqueue(
        db, "draft_questions", body.model_dump(), title=f"Draft {body.count} questions"
    )
    await db.commit()
    return {"job": job_view(job)}


@router.get("/questions/export")
async def export(db: Db, _: Admin) -> Response:
    rows = (
        await db.execute(
            select(models.Question, models.Document)
            .outerjoin(models.Document, models.Question.document_id == models.Document.id)
            .order_by(models.Question.id)
        )
    ).all()
    return Response(
        dumps(export_file([(q, d) for q, d in rows])),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="questions.json"'},
    )


@router.post("/questions/import")
async def import_questions(file: UploadFile, db: Db, _: Admin) -> dict[str, object]:
    try:
        data = json.loads(await file.read())
        return await import_file(db, data)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
