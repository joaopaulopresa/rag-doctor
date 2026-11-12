"""A job queue in PostgreSQL: the API enqueues, the worker claims with SKIP LOCKED."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ragdoctor import models


async def enqueue(
    db: AsyncSession, kind: str, payload: dict[str, Any], *, title: str
) -> models.Job:
    """Add a job; the caller commits."""
    job = models.Job(kind=kind, payload=payload, title=title)
    db.add(job)
    await db.flush()
    return job


async def claim(db: AsyncSession) -> models.Job | None:
    """Mark the oldest queued job as running and return it, or ``None`` if there is none."""
    job = await db.scalar(
        select(models.Job)
        .where(models.Job.status == "queued")
        .order_by(models.Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await db.commit()
    return job


async def finish(
    factory: async_sessionmaker[AsyncSession],
    job_id: int,
    *,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    """Mark a job done (or failed when ``error`` is set)."""
    async with factory() as db:
        await db.execute(
            update(models.Job)
            .where(models.Job.id == job_id)
            .values(
                status="failed" if error else "done",
                result=result or {},
                error=error,
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def requeue_interrupted(db: AsyncSession) -> int:
    """Put jobs left running by a stopped worker back in the queue; return how many."""
    result = await db.execute(
        update(models.Job).where(models.Job.status == "running").values(status="queued")
    )
    await db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


class JobProgress:
    """Receives progress events and writes them to the job row about once a second.

    It satisfies the engine's ``Progress`` protocol (synchronous ``start``, ``advance`` and
    ``note``), so the engine's experiment runner can report through it.

    Args:
        factory: Session factory used for the writes.
        job_id: The job being reported on.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession], job_id: int) -> None:
        self._factory = factory
        self._job_id = job_id
        self.title = ""
        self.done = 0
        self.total = 0
        self.message = ""
        self._dirty = True
        self._task: asyncio.Task[None] | None = None

    def start(self, title: str, total: int) -> None:
        """A unit of work with ``total`` steps begins."""
        self.message, self.done, self.total, self._dirty = title, 0, total, True

    def advance(self, steps: int = 1) -> None:
        """``steps`` steps of the current unit are done."""
        self.done += steps
        self._dirty = True

    def note(self, message: str) -> None:
        """Something worth telling the user happened."""
        self.message, self._dirty = message, True

    async def flush(self) -> None:
        """Write the current state if it changed."""
        if not self._dirty:
            return
        self._dirty = False
        async with self._factory() as db:
            await db.execute(
                update(models.Job)
                .where(models.Job.id == self._job_id)
                .values(done=self.done, total=self.total, message=self.message)
            )
            await db.commit()

    async def __aenter__(self) -> JobProgress:
        async def loop() -> None:
            while True:
                await asyncio.sleep(1.0)
                await self.flush()

        self._task = asyncio.create_task(loop())
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.flush()


def job_view(job: models.Job | None) -> dict[str, Any] | None:
    """Return a job as the screens show it."""
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        "title": job.title,
        "status": job.status,
        "done": job.done,
        "total": job.total,
        "message": job.message,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
