"""Admin: the doctor. Examinations, cases, prescriptions, before/after, external systems."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ragdoctor import models
from ragdoctor.auth import Admin, Db
from ragdoctor.catalog import describe, get_catalog
from ragdoctor.connectors.http import ConnectorError, ExternalSpec, call
from ragdoctor.doctor.compare import compare
from ragdoctor.doctor.diagnosis import LABELS, MEANINGS, Outcome
from ragdoctor.doctor.examine import ERROR, build_summary
from ragdoctor.doctor.report import render_comparison
from ragdoctor.jobs.queue import enqueue, job_view
from ragdoctor.library import load_library
from ragdoctor.routers.lab import start_experiment
from ragdoctor.services.chat import document_titles
from ragdoctor.services.experiments import ExperimentRequest, choose_questions
from ragdoctor.settings import get_settings
from ragdoctor.state import active_activation, spec_of

router = APIRouter(prefix="/api/admin", tags=["doctor"])


@router.get("/outcomes")
async def outcomes(_: Admin) -> dict[str, Any]:
    return {
        "outcomes": [{"id": o.value, "label": LABELS[o], "meaning": MEANINGS[o]} for o in Outcome],
        "judge_model": get_settings().judge_model,
    }


class ExaminationRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    target: Literal["own", "external"] = "own"
    configuration_id: int | None = None
    external_system_id: int | None = None
    questions: int = Field(default=40, ge=1, le=1000)
    same_questions_as: int | None = None


def examination_view(row: models.Examination) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "target_kind": row.target_kind,
        "target": row.target,
        "configuration_id": row.configuration_id,
        "external_system_id": row.external_system_id,
        "questions": len(row.question_ids),
        "baseline_id": row.target.get("baseline_id"),
        "created_at": row.created_at,
        "job": job_view(row.job),
        "summary": row.summary,
    }


@router.get("/examinations")
async def examinations(db: Db, _: Admin) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(models.Examination).order_by(models.Examination.id.desc()).limit(50)
        )
    ).all()
    return {"examinations": [examination_view(row) for row in rows]}


@router.post("/examinations", status_code=status.HTTP_201_CREATED)
async def create_examination(body: ExaminationRequest, db: Db, _: Admin) -> dict[str, Any]:
    library = await load_library(db)
    baseline = None
    if body.same_questions_as is not None:
        baseline = await db.get(models.Examination, body.same_questions_as)
        if baseline is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such examination to repeat.")
        question_ids = list(baseline.question_ids)
    else:
        question_ids = choose_questions(library, min(body.questions, len(library.questions)))
    if not question_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The question set is empty.")
    target: dict[str, Any] = {"baseline_id": baseline.id if baseline else None}
    configuration_id = external_id = None
    if body.target == "own":
        if body.configuration_id is not None:
            configuration = await db.get(models.Configuration, body.configuration_id)
        else:
            activation = await active_activation(db)
            configuration = activation.configuration if activation else None
        if configuration is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No configuration to examine.")
        configuration_id = configuration.id
        target |= {"name": configuration.name, **describe(spec_of(configuration))}
        label = body.label or f"{configuration.name}"
    else:
        system = await db.get(models.ExternalSystem, body.external_system_id or -1)
        if system is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such external system.")
        external_id = system.id
        target |= {"name": system.name, "display": system.name, "url": system.spec.get("url")}
        label = body.label or f"External: {system.name}"
    row = models.Examination(
        label=label,
        target_kind=body.target,
        configuration_id=configuration_id,
        external_system_id=external_id,
        target=target,
        question_ids=question_ids,
    )
    db.add(row)
    await db.flush()
    job = await enqueue(
        db,
        "examination",
        {"examination_id": row.id},
        title=f"Examine {len(question_ids)} questions: {label}",
    )
    row.job_id = job.id
    await db.commit()
    await db.refresh(row)
    return {"examination": examination_view(row)}


async def _examination(db: Db, examination_id: int) -> models.Examination:
    row = await db.get(models.Examination, examination_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such examination.")
    return row


@router.get("/examinations/{examination_id}")
async def examination(examination_id: int, db: Db, _: Admin) -> dict[str, Any]:
    row = await _examination(db, examination_id)
    experiments = (
        await db.scalars(
            select(models.Experiment)
            .where(models.Experiment.examination_id == examination_id)
            .order_by(models.Experiment.id.desc())
        )
    ).all()
    followups = (
        await db.scalars(select(models.Examination).order_by(models.Examination.id.desc()))
    ).all()
    return {
        "examination": examination_view(row),
        "experiments": [
            {
                "id": e.id,
                "name": e.name,
                "purpose": e.purpose,
                "job": job_view(e.job),
                "summary": e.summary,
            }
            for e in experiments
        ],
        "followups": [
            examination_view(f) for f in followups if f.target.get("baseline_id") == row.id
        ],
    }


def case_brief(case: models.ExaminationCase) -> dict[str, Any]:
    data = case.data
    return {
        "id": case.id,
        "question_id": case.question_id,
        "question": data.get("question"),
        "source": data.get("source"),
        "outcome": case.outcome,
        "wrong_gold": case.wrong_gold,
        "scores": data.get("scores"),
        "context_gold_rank": data.get("context_gold_rank"),
        "candidate_gold_rank": data.get("candidate_gold_rank"),
        "error": data.get("error"),
    }


@router.get("/examinations/{examination_id}/cases")
async def cases(
    examination_id: int, db: Db, _: Admin, outcome: str | None = None
) -> dict[str, Any]:
    statement = select(models.ExaminationCase).where(
        models.ExaminationCase.examination_id == examination_id
    )
    if outcome:
        statement = statement.where(models.ExaminationCase.outcome == outcome)
    rows = (await db.scalars(statement.order_by(models.ExaminationCase.question_id))).all()
    return {"cases": [case_brief(row) for row in rows]}


@router.get("/cases/{case_id}")
async def case(case_id: int, db: Db, _: Admin) -> dict[str, Any]:
    row = await db.get(models.ExaminationCase, case_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such case.")
    examination = await _examination(db, row.examination_id)
    data = dict(row.data)
    ids = {p.get("document_id") for p in data.get("context", []) if p.get("document_id")}
    gold = data.get("gold") or {}
    if gold.get("document_id"):
        ids.add(gold["document_id"])
    titles = await document_titles(db, ids)
    for passage in data.get("context", []):
        passage["title"] = titles.get(passage.get("document_id") or "", None)
    if gold:
        gold["title"] = titles.get(gold.get("document_id"), gold.get("document_id"))
    return {
        "case": {**case_brief(row), "data": data},
        "examination": examination_view(examination),
        "meaning": MEANINGS.get(Outcome(row.outcome)) if row.outcome != ERROR else None,
    }


class WrongGold(BaseModel):
    wrong: bool
    note: str = Field(default="", max_length=1000)


@router.post("/cases/{case_id}/wrong-gold")
async def mark_wrong_gold(case_id: int, body: WrongGold, db: Db, _: Admin) -> dict[str, Any]:
    row = await db.get(models.ExaminationCase, case_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such case.")
    data = dict(row.data)
    if body.wrong and not row.wrong_gold:
        data["diagnosed"] = row.outcome
        row.outcome = Outcome.WRONG_GOLD.value
    elif not body.wrong and row.wrong_gold:
        row.outcome = data.pop("diagnosed", row.outcome)
    row.wrong_gold = body.wrong
    row.data = data
    question = await db.get(models.Question, row.question_id)
    if question is not None:
        if body.wrong:
            question.status = "rejected"
            question.note = body.note or f"Marked wrong gold in examination {row.examination_id}."
        elif question.status == "rejected":
            question.status = "accepted"
    await db.flush()
    examination = await _examination(db, row.examination_id)
    examination.summary = await build_summary(db, examination, get_catalog())
    await db.commit()
    return {"case": case_brief(row), "summary": examination.summary}


class PrescribedExperiment(BaseModel):
    outcome: str


@router.post("/examinations/{examination_id}/experiments", status_code=status.HTTP_201_CREATED)
async def run_prescription(
    examination_id: int, body: PrescribedExperiment, db: Db, _: Admin
) -> dict[str, Any]:
    row = await _examination(db, examination_id)
    item = next(
        (p for p in row.summary.get("prescription", []) if p["outcome"] == body.outcome), None
    )
    if item is None or not item.get("plan"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No experiment for this item.")
    plan = item["plan"]
    request = ExperimentRequest(
        name=f"Doctor: {item['label'].lower()} ({plan['focus']})",
        purpose=plan["description"],
        chunkers=plan["chunkers"],
        embedders=plan["embedders"],
        search_modes=plan["search_modes"],
        rerankers=plan["rerankers"],
        generators=plan["generators"],
        context_k=plan["context_k"],
        diversify=plan.get("diversify", "chunker"),
        questions=None,
        question_ids=list(row.question_ids),
    )
    experiment = await start_experiment(db, request, examination_id=row.id)
    return {"experiment": {"id": experiment.id, "job": job_view(experiment.job)}}


async def _comparison(db: Db, before_id: int, after_id: int) -> tuple[Any, ...]:
    before = await _examination(db, before_id)
    after = await _examination(db, after_id)
    rows = (
        await db.scalars(
            select(models.ExaminationCase).where(
                models.ExaminationCase.examination_id.in_((before_id, after_id))
            )
        )
    ).all()

    def outcomes(examination_id: int) -> dict[str, Outcome | str]:
        return {
            r.question_id: (Outcome(r.outcome) if r.outcome != ERROR else ERROR)
            for r in rows
            if r.examination_id == examination_id
        }

    try:
        result = compare(outcomes(before_id), outcomes(after_id))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    texts = {r.question_id: str(r.data.get("question", "")) for r in rows}
    return before, after, result, texts


def _interval(value: Any) -> dict[str, float]:
    return {"mean": value.mean, "low": value.low, "high": value.high}


@router.get("/compare")
async def comparison(before: int, after: int, db: Db, _: Admin) -> dict[str, Any]:
    old, new, result, texts = await _comparison(db, before, after)
    return {
        "before": examination_view(old),
        "after": examination_view(new),
        "questions": result.questions,
        "excluded": result.excluded,
        "counts": result.counts,
        "before_rate": _interval(result.before),
        "after_rate": _interval(result.after),
        "difference": {
            **_interval(result.difference),
            "significant": result.difference.excludes_zero,
        },
        "movements": [
            {
                "question_id": m.question_id,
                "question": texts.get(m.question_id, ""),
                "before": m.before.value,
                "after": m.after.value,
                "change": m.change,
            }
            for m in result.movements
        ],
        "judge_model": get_settings().judge_model,
    }


@router.get("/compare/report", response_class=HTMLResponse)
async def comparison_report(before: int, after: int, db: Db, _: Admin) -> HTMLResponse:
    old, new, result, texts = await _comparison(db, before, after)
    page = render_comparison(
        {"label": old.label, "target": old.target},
        {"label": new.label, "target": new.target, "judge": get_settings().judge_model},
        result,
        texts,
    )
    filename = f"before-after-{before}-{after}.html"
    return HTMLResponse(page, headers={"Content-Disposition": f'inline; filename="{filename}"'})


class ExternalSystemBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    spec: ExternalSpec


def external_view(row: models.ExternalSystem) -> dict[str, Any]:
    spec = ExternalSpec.model_validate(row.spec)
    return {"id": row.id, "name": row.name, "spec": spec.public(), "created_at": row.created_at}


@router.get("/external-systems")
async def external_systems(db: Db, _: Admin) -> dict[str, Any]:
    rows = (
        await db.scalars(select(models.ExternalSystem).order_by(models.ExternalSystem.id))
    ).all()
    return {
        "systems": [external_view(row) for row in rows],
        "mock_url": get_settings().mock_rag_url,
    }


@router.post("/external-systems", status_code=status.HTTP_201_CREATED)
async def create_external(body: ExternalSystemBody, db: Db, _: Admin) -> dict[str, Any]:
    if await db.scalar(
        select(models.ExternalSystem).where(models.ExternalSystem.name == body.name)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A system with this name exists.")
    row = models.ExternalSystem(name=body.name, spec=body.spec.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"system": external_view(row)}


@router.delete("/external-systems/{system_id}")
async def delete_external(system_id: int, db: Db, _: Admin) -> dict[str, bool]:
    row = await db.get(models.ExternalSystem, system_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such system.")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


class ConnectionTest(BaseModel):
    spec: ExternalSpec
    question: str = Field(min_length=3, max_length=1000)


@router.post("/external-systems/test")
async def test_external(body: ConnectionTest, _: Admin) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        try:
            answer, passages, latency, raw = await call(body.spec, body.question, client)
        except ConnectorError as error:
            return {"ok": False, "error": str(error)}
    return {
        "ok": True,
        "answer": answer,
        "passages": (
            [{"text": p.text, "document_id": p.document_id, "span": p.span} for p in passages]
            if passages is not None
            else None
        ),
        "latency_s": latency,
        "raw": raw,
    }
