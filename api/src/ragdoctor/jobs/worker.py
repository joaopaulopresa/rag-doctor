"""The background worker: claims jobs one at a time and runs them on one engine session."""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import ragbench as rb

from ragdoctor import models
from ragdoctor.catalog import get_catalog
from ragdoctor.db import session_factory
from ragdoctor.doctor.examine import run_examination
from ragdoctor.jobs.queue import JobProgress, claim, finish, requeue_interrupted
from ragdoctor.rag import Rag, open_rag
from ragdoctor.services.experiments import run_experiment_job
from ragdoctor.services.indexing import index_library
from ragdoctor.services.questions import draft_questions
from ragdoctor.settings import get_settings

logger = logging.getLogger(__name__)

Handler = Callable[[Rag, models.Job, JobProgress], Awaitable[dict[str, Any]]]


async def _index(rag: Rag, job: models.Job, progress: JobProgress) -> dict[str, Any]:
    progress.note("Chunking and embedding the documents")
    spec = (
        rb.PipelineConfig.model_validate(job.payload["spec"]) if job.payload.get("spec") else None
    )
    async with session_factory()() as db:
        return await index_library(db, rag, spec)


async def _draft(rag: Rag, job: models.Job, progress: JobProgress) -> dict[str, Any]:
    progress.note("Drafting questions with the question-writing model")
    async with session_factory()() as db:
        return await draft_questions(
            db, rag, int(job.payload.get("count", 10)), int(job.payload.get("seed", 0))
        )


async def _experiment(rag: Rag, job: models.Job, progress: JobProgress) -> dict[str, Any]:
    return await run_experiment_job(
        session_factory(),
        rag,
        get_catalog(),
        get_settings(),
        job.payload["experiment_id"],
        progress,
    )


async def _examination(rag: Rag, job: models.Job, progress: JobProgress) -> dict[str, Any]:
    return await run_examination(
        session_factory(), rag, get_catalog(), job.payload["examination_id"], progress
    )


HANDLERS: dict[str, Handler] = {
    "index": _index,
    "draft_questions": _draft,
    "experiment": _experiment,
    "examination": _examination,
}


async def run_one(rag: Rag) -> bool:
    """Run the next queued job; return whether there was one."""
    factory = session_factory()
    async with factory() as db:
        job = await claim(db)
    if job is None:
        return False
    logger.info("job %d (%s) started", job.id, job.kind)
    try:
        async with JobProgress(factory, job.id) as progress:
            result = await HANDLERS[job.kind](rag, job, progress)
    except Exception as error:  # a failed job must not stop the worker
        logger.error("job %d failed: %s\n%s", job.id, error, traceback.format_exc())
        await finish(factory, job.id, error=f"{type(error).__name__}: {error}")
    else:
        logger.info("job %d done: %s", job.id, result)
        await finish(factory, job.id, result=result)
    return True


async def main() -> None:
    """Run jobs until stopped."""
    settings = get_settings()
    async with session_factory()() as db:
        requeued = await requeue_interrupted(db)
    if requeued:
        logger.info("requeued %d interrupted job(s)", requeued)
    async with open_rag(settings) as rag:
        logger.info("worker ready")
        while True:
            if not await run_one(rag):
                await asyncio.sleep(1.0)
