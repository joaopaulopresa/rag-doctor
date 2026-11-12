"""The chat: answer a question with the active configuration and keep the exchange."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import ragbench as rb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models
from ragdoctor.rag import Rag
from ragdoctor.services.indexing import index_exists
from ragdoctor.state import active_activation, live_collection, spec_of


class ChatUnavailableError(Exception):
    """The chat cannot answer yet (no configuration, or its index is still being built)."""


async def document_titles(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    """Return the title of each document id."""
    if not ids:
        return {}
    rows = await db.execute(
        select(models.Document.id, models.Document.title).where(models.Document.id.in_(ids))
    )
    return {row.id: row.title for row in rows}


def usage_view(usage: rb.Usage) -> dict[str, float]:
    """Return a usage as plain numbers."""
    return {
        "cost_usd": usage.cost_usd,
        "paid_usd": usage.paid_usd,
        "latency_s": usage.latency_s,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }


def passages_view(
    chunks: tuple[rb.RetrievedChunk, ...], titles: dict[str, str]
) -> list[dict[str, Any]]:
    """Return retrieved passages numbered as the answer cites them."""
    return [
        {
            "number": number,
            "document_id": chunk.document_id,
            "title": titles.get(chunk.document_id, chunk.document_id),
            "start": chunk.span.start,
            "end": chunk.span.end,
            "text": chunk.text,
            "score": chunk.score,
        }
        for number, chunk in enumerate(chunks, start=1)
    ]


async def resolve_live(db: AsyncSession, rag: Rag) -> tuple[models.Configuration, str]:
    """Return the active configuration and the collection it searches.

    Raises:
        ChatUnavailableError: If nothing is active or indexed yet.
    """
    activation = await active_activation(db)
    collection = await live_collection(db)
    if activation is None or collection is None:
        raise ChatUnavailableError("The library is being prepared. Try again in a minute.")
    spec = spec_of(activation.configuration)
    if spec.generator is None:
        raise ChatUnavailableError("The active configuration has no generator.")
    if not await index_exists(rag, spec, collection):
        raise ChatUnavailableError("The index of the active configuration is being built.")
    return activation.configuration, collection


async def ask(db: AsyncSession, rag: Rag, question: str) -> AsyncIterator[dict[str, Any]]:
    """Answer ``question``, yielding events as each step finishes.

    Events: ``status`` (a step started), ``passages`` (the context, before the answer exists),
    ``answer`` (text and checked citations) and ``done`` (message id and usage).
    """
    configuration, collection = await resolve_live(db, rag)
    spec = spec_of(configuration)
    pipeline = rag.pipeline(spec, collection)
    yield {"type": "status", "step": "searching", "configuration": spec.display}
    retrieved = await pipeline.retrieve(question)
    titles = await document_titles(db, {chunk.document_id for chunk in retrieved.chunks})
    yield {"type": "passages", "passages": passages_view(retrieved.chunks, titles)}
    yield {"type": "status", "step": "writing"}
    # Retrieval and reranking are served from the cache on this second pass.
    answer = await pipeline.answer(question)
    titles |= await document_titles(
        db, {chunk.document_id for chunk in answer.chunks} - set(titles)
    )
    passages = passages_view(answer.chunks, titles)
    message = models.ChatMessage(
        question=question,
        answer=answer.text,
        passages=passages,
        citations=list(answer.citations),
        config_key=spec.key,
        usage=usage_view(answer.usage + retrieved.usage),
    )
    db.add(message)
    await db.commit()
    yield {
        "type": "answer",
        "text": answer.text,
        "citations": list(answer.citations),
        "invalid_citations": list(answer.invalid_citations),
        "passages": passages,
    }
    yield {
        "type": "done",
        "message_id": message.id,
        "usage": message.usage,
        "configuration": spec.display,
    }
