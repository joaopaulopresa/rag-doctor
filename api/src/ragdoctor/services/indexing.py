"""Keeps the active configuration's index in step with the library."""

from __future__ import annotations

import logging
from typing import Any

import ragbench as rb
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models
from ragdoctor.library import load_library
from ragdoctor.rag import Rag
from ragdoctor.state import LIBRARY_KEY, active_activation, set_state, spec_of

logger = logging.getLogger(__name__)


async def index_library(
    db: AsyncSession, rag: Rag, spec: rb.PipelineConfig | None = None
) -> dict[str, Any]:
    """Index every pending and ready document for ``spec`` (default: the active configuration).

    Documents that cannot be chunked are marked failed; the others become ready and the
    collection they form becomes the one the chat searches.

    Returns:
        The collection, the number of chunks and what the embeddings cost now.
    """
    if spec is None:
        activation = await active_activation(db)
        if activation is None:
            raise rb.ConfigError("no active configuration")
        spec = spec_of(activation.configuration)
    library = await load_library(db, include_pending=True)
    if not library.documents:
        return {"collection": None, "chunks": 0, "paid_usd": 0.0}
    pipeline = rag.pipeline(spec, library.collection)
    report = await pipeline.index(library.documents)
    await db.execute(
        update(models.Document)
        .where(models.Document.status == "pending")
        .values(status="ready", error="")
    )
    await set_state(
        db,
        LIBRARY_KEY,
        {"collection": library.collection, "documents": len(library.documents)},
    )
    await db.commit()
    logger.info("index %s: %d chunks, $%.4f", report.index, report.chunks, report.usage.paid_usd)
    return {
        "collection": library.collection,
        "index": report.index,
        "chunks": report.chunks,
        "built": report.built,
        "paid_usd": report.usage.paid_usd,
    }


async def index_exists(rag: Rag, spec: rb.PipelineConfig, collection: str) -> bool:
    """Return whether ``spec`` already has a complete index of ``collection``."""
    return await rag.session.store.has_index(rag.pipeline(spec, collection).index_name)
