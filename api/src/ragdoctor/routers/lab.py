"""Admin: catalogue, configurations and their history, playground, experiments, jobs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import ragbench as rb
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ragdoctor import models
from ragdoctor.auth import Admin, Db
from ragdoctor.catalog import Selection, describe, get_catalog
from ragdoctor.db import session_factory
from ragdoctor.jobs.queue import enqueue, job_view
from ragdoctor.routers.deps import RagDep
from ragdoctor.services.chat import document_titles, passages_view, usage_view
from ragdoctor.services.experiments import ExperimentRequest
from ragdoctor.services.indexing import index_exists
from ragdoctor.settings import get_settings
from ragdoctor.state import active_activation, live_collection, save_configuration, spec_of

router = APIRouter(prefix="/api/admin", tags=["lab"])


def configuration_view(row: models.Configuration) -> dict[str, Any]:
    spec = spec_of(row)
    selection = get_catalog().selection(spec)
    return {
        "id": row.id,
        "name": row.name,
        "origin": row.origin,
        "created_at": row.created_at,
        "selection": selection.model_dump() if selection else None,
        **describe(spec),
    }


@router.get("/catalog")
async def catalog(_: Admin) -> dict[str, Any]:
    return get_catalog().public()


@router.get("/configurations")
async def configurations(db: Db, rag: RagDep, _: Admin) -> dict[str, Any]:
    activation = await active_activation(db)
    history = (
        await db.scalars(select(models.Activation).order_by(models.Activation.id.desc()).limit(50))
    ).all()
    collection = await live_collection(db)
    active = None
    if activation is not None:
        spec = spec_of(activation.configuration)
        active = {
            **configuration_view(activation.configuration),
            "activated_at": activation.activated_at,
            "index_ready": bool(collection) and await index_exists(rag, spec, collection or ""),
        }
    return {
        "active": active,
        "history": [
            {
                "activation_id": item.id,
                "note": item.note,
                "activated_by": item.activated_by,
                "activated_at": item.activated_at,
                "active": activation is not None and item.id == activation.id,
                "configuration": configuration_view(item.configuration),
            }
            for item in history
        ],
    }


class Apply(BaseModel):
    selection: Selection | None = None
    spec: dict[str, Any] | None = None
    configuration_id: int | None = None
    name: str | None = Field(default=None, max_length=200)
    note: str = Field(default="", max_length=200)
    origin: str = Field(default="", max_length=200)


def resolve_spec(body: Apply) -> rb.PipelineConfig:
    try:
        if body.selection is not None:
            return get_catalog().pipeline(body.selection)
        if body.spec is not None:
            spec = rb.PipelineConfig.model_validate(body.spec)
            if get_catalog().selection(spec) is None:
                raise ValueError("the configuration uses a component that is not in the catalogue")
            return spec
    except (ValueError, rb.ConfigError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a selection or a spec.")


@router.post("/configurations/apply")
async def apply(body: Apply, db: Db, rag: RagDep, admin: Admin) -> dict[str, Any]:
    if body.configuration_id is not None:
        configuration = await db.get(models.Configuration, body.configuration_id)
        if configuration is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such configuration.")
    else:
        spec = resolve_spec(body)
        configuration = await save_configuration(db, spec, name=body.name, origin=body.origin)
    spec = spec_of(configuration)
    if spec.generator is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The chat needs a generator.")
    db.add(
        models.Activation(
            configuration_id=configuration.id,
            note=body.note or "Applied from the lab",
            activated_by=admin.email,
        )
    )
    collection = await live_collection(db)
    job = None
    if collection is None or not await index_exists(rag, spec, collection):
        job = await enqueue(db, "index", {}, title=f"Index for {spec.display}")
    await db.commit()
    return {"configuration": configuration_view(configuration), "job": job_view(job)}


class PlaygroundRequest(BaseModel):
    selection: Selection
    question: str = Field(min_length=3, max_length=1000)


@router.post("/playground")
async def playground(body: PlaygroundRequest, db: Db, rag: RagDep, _: Admin) -> dict[str, Any]:
    try:
        spec = get_catalog().pipeline(body.selection)
    except (ValueError, rb.ConfigError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    collection = await live_collection(db)
    if collection is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The library is not indexed yet.")
    if not await index_exists(rag, spec, collection):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "index_missing", "message": "This configuration has no index yet."},
        )
    pipeline = rag.pipeline(spec, collection)
    answer = await (pipeline.answer if spec.generator else pipeline.retrieve)(body.question)
    titles = await document_titles(db, {chunk.document_id for chunk in answer.chunks})
    return {
        "configuration": describe(spec),
        "answer": answer.text,
        "citations": list(answer.citations),
        "invalid_citations": list(answer.invalid_citations),
        "passages": passages_view(answer.chunks, titles),
        "usage": {
            "retrieval": usage_view(answer.retrieval_usage),
            "rerank": usage_view(answer.rerank_usage),
            "generation": usage_view(answer.generation_usage),
            "total": usage_view(answer.usage),
        },
    }


@router.post("/playground/index")
async def build_index(body: Selection, db: Db, _: Admin) -> dict[str, Any]:
    try:
        spec = get_catalog().pipeline(body)
    except (ValueError, rb.ConfigError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    job = await enqueue(
        db, "index", {"spec": spec.model_dump(mode="json")}, title=f"Index for {spec.display}"
    )
    await db.commit()
    return {"job": job_view(job)}


def experiment_view(row: models.Experiment) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "config": row.config,
        "run_id": row.run_id,
        "examination_id": row.examination_id,
        "created_at": row.created_at,
        "job": job_view(row.job),
        "summary": row.summary,
    }


@router.get("/experiments")
async def experiments(db: Db, _: Admin) -> dict[str, Any]:
    rows = (
        await db.scalars(select(models.Experiment).order_by(models.Experiment.id.desc()).limit(50))
    ).all()
    return {"experiments": [experiment_view(row) for row in rows]}


async def start_experiment(
    db: Db, request: ExperimentRequest, *, examination_id: int | None = None
) -> models.Experiment:
    """Validate ``request`` against the catalogue, store it and queue it."""
    catalog = get_catalog()
    try:
        for kind, ids in (
            ("chunkers", request.chunkers),
            ("embedders", request.embedders),
            ("rerankers", request.rerankers),
            ("generators", request.generators),
        ):
            for option_id in ids:
                catalog.option(kind, option_id)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    experiment = models.Experiment(
        name=request.name,
        purpose=request.purpose,
        config=request.model_dump(),
        examination_id=examination_id,
    )
    db.add(experiment)
    await db.flush()
    job = await enqueue(
        db, "experiment", {"experiment_id": experiment.id}, title=f"Experiment: {request.name}"
    )
    experiment.job_id = job.id
    await db.commit()
    await db.refresh(experiment)
    return experiment


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
async def create_experiment(body: ExperimentRequest, db: Db, _: Admin) -> dict[str, Any]:
    return {"experiment": experiment_view(await start_experiment(db, body))}


@router.get("/experiments/{experiment_id}")
async def experiment(experiment_id: int, db: Db, _: Admin) -> dict[str, Any]:
    row = await db.get(models.Experiment, experiment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such experiment.")
    return {"experiment": experiment_view(row)}


@router.get("/experiments/{experiment_id}/report")
async def experiment_report(experiment_id: int, db: Db, _: Admin) -> FileResponse:
    row = await db.get(models.Experiment, experiment_id)
    path = Path(str((row.summary if row else {}).get("report_path", "")))
    reports = (get_settings().data_dir / "reports").resolve()
    if row is None or not path.is_file() or reports not in path.resolve().parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The report is not ready.")
    return FileResponse(path, media_type="text/html")


@router.get("/jobs")
async def jobs(db: Db, _: Admin, active: bool = False) -> dict[str, Any]:
    statement = select(models.Job).order_by(models.Job.id.desc()).limit(30)
    if active:
        statement = statement.where(models.Job.status.in_(("queued", "running")))
    return {"jobs": [job_view(job) for job in (await db.scalars(statement)).all()]}


@router.get("/jobs/{job_id}")
async def job(job_id: int, db: Db, _: Admin) -> dict[str, Any]:
    row = await db.get(models.Job, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
    return {"job": job_view(row)}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, request: Request, _: Admin) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        last = None
        while not await request.is_disconnected():
            async with session_factory()() as db:
                row = await db.get(models.Job, job_id)
                view = job_view(row)
            payload = json.dumps(view, default=str)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if view is None or view["status"] in ("done", "failed"):
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
