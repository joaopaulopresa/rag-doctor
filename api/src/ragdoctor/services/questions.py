"""The question set: drafting, reviewing, importing and exporting gold questions."""

from __future__ import annotations

import json
import re
from typing import Any

import ragbench as rb
from ragbench.experiment.questions import generate_questions, locate_quote
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models
from ragdoctor.library import load_library
from ragdoctor.rag import Rag


def question_view(row: models.Question, document: models.Document | None) -> dict[str, Any]:
    """Return a question with the text of its evidence."""
    evidence = []
    if document is not None:
        evidence = [document.text[start:end] for start, end in row.spans]
    return {
        "id": row.id,
        "text": row.text,
        "document_id": row.document_id,
        "document_title": document.title if document else None,
        "spans": row.spans,
        "evidence": evidence,
        "source": row.source,
        "status": row.status,
        "origin": row.origin,
        "note": row.note,
        "updated_at": row.updated_at,
    }


def locate_evidence(text: str, quote: str) -> list[int]:
    """Return ``[start, end]`` of ``quote`` in ``text``.

    Raises:
        ValueError: If the quote is not found exactly once.
    """
    span = locate_quote(text, quote, rb.Span(0, len(text)))
    if span is None:
        raise ValueError(
            "the evidence must be copied from the document and occur in it exactly once"
        )
    return [span.start, span.end]


async def next_id(db: AsyncSession, prefix: str) -> str:
    """Return a new question id ``<prefix>-NNNN``."""
    count = await db.scalar(
        select(func.count())
        .select_from(models.Question)
        .where(models.Question.id.like(f"{prefix}-%"))
    )
    number = int(count or 0)
    while await db.get(models.Question, f"{prefix}-{number:04d}") is not None:
        number += 1
    return f"{prefix}-{number:04d}"


async def draft_questions(db: AsyncSession, rag: Rag, count: int, seed: int) -> dict[str, Any]:
    """Draft up to ``count`` candidate questions with the question-writing model.

    The engine picks passages in code; the model only writes a question and quotes its
    evidence, and a reply whose quote is not found in the passage is discarded.
    """
    library = await load_library(db)
    drafts, usage = await generate_questions(
        library.corpus, rag.question_writer(), count=count, seed=seed
    )
    created = 0
    for draft in drafts:
        db.add(
            models.Question(
                id=await next_id(db, "draft"),
                text=draft.query,
                document_id=draft.document_id,
                spans=[[draft.span.start, draft.span.end]],
                source=next((d.source for d in library.documents if d.id == draft.document_id), ""),
                status="draft",
                origin="generated",
            )
        )
        await db.flush()
        created += 1
    await db.commit()
    return {"tried": count, "created": created, "paid_usd": usage.paid_usd}


async def from_feedback(db: AsyncSession, message: models.ChatMessage) -> models.Question:
    """Put a chat question that got a thumbs-down into the review queue."""
    existing = await db.scalar(
        select(models.Question).where(
            models.Question.text == message.question, models.Question.origin == "feedback"
        )
    )
    if existing is not None:
        return existing
    question = models.Question(
        id=await next_id(db, "feedback"),
        text=message.question,
        document_id=None,
        spans=[],
        status="draft",
        origin="feedback",
        note="Thumbs-down in the chat. Add the gold evidence before accepting.",
    )
    db.add(question)
    await db.flush()
    return question


def export_file(rows: list[tuple[models.Question, models.Document | None]]) -> dict[str, Any]:
    """Return questions in the engine's question-file format (``{"tests": [...]}``)."""
    tests = []
    for row, document in rows:
        if document is None or not row.spans:
            continue
        tests.append(
            {
                "id": row.id,
                "query": row.text,
                "reviewed": row.status == "accepted",
                "status": row.status,
                "snippets": [
                    {
                        "file_path": row.document_id,
                        "span": [start, end],
                        "answer": document.text[start:end],
                    }
                    for start, end in row.spans
                ],
            }
        )
    return {"tests": tests}


async def import_file(db: AsyncSession, data: Any) -> dict[str, int]:
    """Add or update questions from a question file; return what happened.

    Each snippet must point to a document of the library and its ``answer`` must equal the
    document text at ``span``, the same check the engine's folder loader makes.

    Raises:
        ValueError: If the file is not a question file.
    """
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise ValueError('a question file is a JSON object with a "tests" list')
    added = updated = skipped = 0
    for test in data["tests"]:
        try:
            snippets = test["snippets"]
            document_id = snippets[0]["file_path"]
            document = await db.get(models.Document, document_id)
            if document is None:
                raise KeyError(document_id)
            spans = []
            for snippet in snippets:
                start, end = (int(v) for v in snippet["span"])
                if (
                    snippet["file_path"] != document_id
                    or document.text[start:end] != snippet["answer"]
                ):
                    raise ValueError("span does not match its answer")
                spans.append([start, end])
            text = str(test["query"]).strip()
        except (KeyError, TypeError, ValueError, IndexError):
            skipped += 1
            continue
        status = test.get("status") or ("accepted" if test.get("reviewed") else "draft")
        if status not in ("draft", "accepted", "rejected"):
            status = "draft"
        question_id = str(test.get("id") or "")
        if question_id and not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", question_id):
            question_id = ""
        row = await db.get(models.Question, question_id) if question_id else None
        if row is None:
            db.add(
                models.Question(
                    id=question_id or await next_id(db, "imported"),
                    text=text,
                    document_id=document_id,
                    spans=spans,
                    source=document.source,
                    status=status,
                    origin="imported",
                )
            )
            added += 1
        else:
            row.text, row.document_id, row.spans, row.status = text, document_id, spans, status
            updated += 1
        await db.flush()
    await db.commit()
    return {"added": added, "updated": updated, "skipped": skipped}


def dumps(data: dict[str, Any]) -> str:
    """Serialise a question file."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
