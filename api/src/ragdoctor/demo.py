"""First start: demo accounts, the demo corpus with its question set, the initial configuration."""

from __future__ import annotations

import logging
from typing import Any

import ragbench as rb
from ragbench.components.caches import MemoryCache
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models
from ragdoctor.auth import ensure_user
from ragdoctor.catalog import get_catalog
from ragdoctor.jobs.queue import enqueue
from ragdoctor.settings import get_settings
from ragdoctor.state import active_activation, get_state, save_configuration, set_state

logger = logging.getLogger(__name__)

DEMO_KEY = "demo"
#: The rag-bench demo corpus: LegalBench-RAG, the upstream "mini" sample of three sources.
DEMO_CORPUS = rb.ComponentConfig(
    name="legalbench_rag",
    params={"sources": ["privacy_qa", "contractnli", "cuad"], "mini": 194},
)


async def load_demo_corpus(db: AsyncSession) -> dict[str, Any]:
    """Store the demo documents and their reviewed questions as the library."""
    settings = get_settings()
    resources = rb.Resources(cache=MemoryCache(), data_dir=settings.data_dir)
    corpus = rb.load_corpus(DEMO_CORPUS, resources)
    for document in corpus.documents:
        db.add(
            models.Document(
                id=document.id,
                title=document.title,
                source=document.source,
                text=document.text,
                origin="dataset",
                status="pending",
            )
        )
    await db.flush()
    for question in corpus.questions:
        db.add(
            models.Question(
                id=question.id,
                text=question.text,
                document_id=question.document_id,
                spans=[[span.start, span.end] for span in question.spans],
                source=question.source,
                status="accepted",
                origin="dataset",
            )
        )
    return {
        "corpus": corpus.name,
        "revision": corpus.revision,
        "licences": dict(corpus.licences),
        "documents": len(corpus.documents),
        "questions": len(corpus.questions),
    }


def ensure_demo_files() -> None:
    """Download the demo corpus files if they are missing (the mock service reads them too)."""
    settings = get_settings()
    rb.load_corpus(DEMO_CORPUS, rb.Resources(cache=MemoryCache(), data_dir=settings.data_dir))


async def reset(db: AsyncSession) -> None:
    """Delete the application's data, keeping users and the engine's cache, indexes and runs.

    Used to bring a demo back to its first state; replaying it then costs nothing.
    """
    for table in (
        "examination_cases",
        "examinations",
        "experiments",
        "external_systems",
        "chat_messages",
        "jobs",
        "activations",
        "configurations",
        "questions",
        "documents",
        "app_state",
    ):
        await db.execute(text(f"DELETE FROM {table}"))
    await db.commit()


async def bootstrap(db: AsyncSession) -> None:
    """Prepare a fresh database; safe to run on every start."""
    settings = get_settings()
    await ensure_user(db, settings.admin_email, settings.admin_password, "admin")
    await ensure_user(db, settings.user_email, settings.user_password, "user")
    await db.commit()

    if not await get_state(db, DEMO_KEY):
        documents = await db.scalar(select(func.count()).select_from(models.Document))
        info = await load_demo_corpus(db) if not documents else {"skipped": True}
        await set_state(db, DEMO_KEY, info)
        await db.commit()
        logger.info("demo data: %s", info)

    if await active_activation(db) is None:
        catalog = get_catalog()
        spec = catalog.pipeline(catalog.initial)
        configuration = await save_configuration(
            db, spec, name="Recommended by rag-bench", origin="rag-bench demo report"
        )
        db.add(
            models.Activation(
                configuration_id=configuration.id,
                note="Initial configuration",
                activated_by="system",
            )
        )
        await enqueue(db, "index", {}, title="Index the library")
        await db.commit()
        logger.info("initial configuration %s, indexing queued", spec.display)
