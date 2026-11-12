"""Runs an examination: ask every question, judge the answer, locate the failure.

The same loop examines this application's own pipeline and an external system; only the
`Target` differs. What a target exposes decides how precise the diagnosis can be.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import ragbench as rb
from ragbench.experiment.stats import bootstrap_mean
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ragdoctor import models
from ragdoctor.catalog import Catalog
from ragdoctor.connectors.http import ConnectorError, ExternalSpec, call
from ragdoctor.doctor.diagnosis import LABELS, Evidence, Outcome, diagnose, summarise
from ragdoctor.doctor.evidence import Gold, Passage, first_gold_rank, holds_gold
from ragdoctor.doctor.prescription import prescribe
from ragdoctor.jobs.queue import JobProgress
from ragdoctor.library import load_library
from ragdoctor.rag import Rag
from ragdoctor.state import spec_of

logger = logging.getLogger(__name__)

PROBE_DEPTH = 20
CONCURRENCY = 4
ERROR = "error"


@dataclass(frozen=True, slots=True)
class Observation:
    """What a target returned for one question.

    Attributes:
        answer: The answer text.
        context: Passages given to the generator, in citation order; ``None`` if the target
            returns none.
        candidates: Passages retrieved before the cut to the context size; ``None`` if the
            target does not expose them.
        cost_usd, paid_usd, latency_s: What answering cost and took (zero for external
            systems, whose bill is not visible).
    """

    answer: str
    context: list[Passage] | None
    candidates: list[Passage] | None
    cost_usd: float = 0.0
    paid_usd: float = 0.0
    latency_s: float = 0.0


class Target(Protocol):
    """A RAG system under examination."""

    async def observe(self, question: str) -> Observation:
        """Ask ``question`` and return what came back."""
        ...


def _passages(chunks: tuple[rb.RetrievedChunk, ...]) -> list[Passage]:
    return [Passage(c.text, c.document_id, (c.span.start, c.span.end)) for c in chunks]


class OwnTarget:
    """This application's pipeline. Candidates come from a probe of the first search stage.

    For a configuration with a reranker, the probe returns the candidates the reranker sees;
    without one, it returns the top ``PROBE_DEPTH`` search results. A gold passage among them
    but missing from the context was found and then ranked out.
    """

    def __init__(self, rag: Rag, spec: rb.PipelineConfig, collection: str) -> None:
        self.pipeline = rag.pipeline(spec, collection)
        depth = spec.candidates if spec.reranker is not None else PROBE_DEPTH
        probe = spec.model_copy(
            update={"reranker": None, "generator": None, "top_k": max(depth, spec.top_k)}
        )
        self.probe = rag.pipeline(probe, collection)

    async def observe(self, question: str) -> Observation:
        """Answer with the pipeline and probe the candidates."""
        answer = await self.pipeline.answer(question)
        probe = await self.probe.retrieve(question)
        usage = answer.usage + probe.usage
        return Observation(
            answer=answer.text,
            context=_passages(answer.chunks),
            candidates=_passages(probe.chunks),
            cost_usd=usage.cost_usd,
            paid_usd=usage.paid_usd,
            latency_s=answer.usage.latency_s,
        )


class ExternalTarget:
    """An external system reached through the HTTP connector. It exposes no candidates."""

    def __init__(self, spec: ExternalSpec, client: httpx.AsyncClient) -> None:
        self.spec = spec
        self.client = client

    async def observe(self, question: str) -> Observation:
        """Call the system."""
        answer, passages, latency, _ = await call(self.spec, question, self.client)
        return Observation(answer=answer, context=passages, candidates=None, latency_s=latency)


def gold_of(question: rb.Question, document_text: str) -> Gold:
    """Return the gold evidence of ``question``."""
    spans = tuple((span.start, span.end) for span in question.spans)
    return Gold(
        document_id=question.document_id,
        spans=spans,
        texts=tuple(document_text[start:end] for start, end in spans),
    )


async def examine_question(
    target: Target, judge: rb.Judge, question: rb.Question, gold: Gold
) -> tuple[Outcome, dict[str, Any]]:
    """Examine one question; return its outcome and everything the case screen shows.

    Raises:
        ProviderError: If the judge or a model of the pipeline fails.
        ConnectorError: If an external system fails.
    """
    observation = await target.observe(question.text)
    context = observation.context
    verdict = await judge.judge(
        question=question.text,
        answer=observation.answer,
        gold=list(gold.texts),
        context=[passage.text for passage in context or []],
    )
    context_rank = first_gold_rank(context, gold) if context is not None else None
    candidate_rank = (
        first_gold_rank(observation.candidates, gold)
        if observation.candidates is not None
        else None
    )
    evidence = Evidence(
        correctness=verdict.correctness,
        faithfulness=verdict.faithfulness,
        gold_in_candidates=(
            candidate_rank is not None if observation.candidates is not None else None
        ),
        gold_in_context=context_rank is not None if context is not None else None,
    )
    outcome = diagnose(evidence)
    data = {
        "question": question.text,
        "source": question.source,
        "gold": {
            "document_id": gold.document_id,
            "spans": [list(span) for span in gold.spans],
            "texts": list(gold.texts),
        },
        "answer": observation.answer,
        "context": [
            {
                "number": number,
                "text": passage.text,
                "document_id": passage.document_id,
                "span": list(passage.span) if passage.span else None,
                "holds_gold": holds_gold(passage, gold),
            }
            for number, passage in enumerate(context or [], start=1)
        ],
        "has_context": context is not None,
        "context_gold_rank": context_rank,
        "candidates": len(observation.candidates) if observation.candidates is not None else None,
        "candidate_gold_rank": candidate_rank,
        "scores": verdict.scores(),
        "rationale": verdict.rationale,
        "cost_usd": observation.cost_usd + verdict.usage.cost_usd,
        "paid_usd": observation.paid_usd + verdict.usage.paid_usd,
        "judge_cost_usd": verdict.usage.cost_usd,
        "latency_s": observation.latency_s,
    }
    return outcome, data


def _clean(value: float) -> float | None:
    return None if math.isnan(value) else value


async def build_summary(
    db: AsyncSession, examination: models.Examination, catalog: Catalog
) -> dict[str, Any]:
    """Compute the totals and the prescription of an examination from its cases."""
    cases = (
        await db.scalars(
            select(models.ExaminationCase)
            .where(models.ExaminationCase.examination_id == examination.id)
            # Question order, as in the before/after comparison, so the same questions give
            # the same bootstrap interval on both pages.
            .order_by(models.ExaminationCase.question_id)
        )
    ).all()
    outcomes = [Outcome(case.outcome) for case in cases if case.outcome != ERROR]
    summary = summarise(outcomes)
    counted = [o for o in outcomes if o is not Outcome.WRONG_GOLD]
    interval = (
        bootstrap_mean([1.0 if o is Outcome.CORRECT else 0.0 for o in counted], seed=0)
        if counted
        else None
    )
    selection = None
    if examination.target_kind == "own" and examination.configuration is not None:
        selection = catalog.selection(spec_of(examination.configuration))
    items = prescribe(
        summary, current=selection, catalog=catalog, external=examination.target_kind != "own"
    )
    return {
        "total": len(cases),
        "evaluated": summary.evaluated,
        "errors": len(cases) - len(outcomes),
        "counts": {outcome.value: count for outcome, count in summary.counts.items()},
        "labels": {outcome.value: label for outcome, label in LABELS.items()},
        "correct_rate": summary.correct_rate,
        "correct_low": _clean(interval.low) if interval else None,
        "correct_high": _clean(interval.high) if interval else None,
        "failures": [[outcome.value, count] for outcome, count in summary.failures],
        "cost_usd": sum(float(case.data.get("cost_usd") or 0) for case in cases),
        "paid_usd": sum(float(case.data.get("paid_usd") or 0) for case in cases),
        "judge_cost_usd": sum(float(case.data.get("judge_cost_usd") or 0) for case in cases),
        "prescription": [
            {
                "outcome": item.outcome.value,
                "label": LABELS[item.outcome],
                "count": item.count,
                "share": item.share,
                "stage": item.stage,
                "candidates": item.candidates,
                "same_plan_as": item.same_plan_as.value if item.same_plan_as else None,
                "notes": item.notes,
                "plan": (
                    {
                        "focus": item.plan.focus,
                        "description": item.plan.description,
                        "chunkers": item.plan.chunkers,
                        "embedders": item.plan.embedders,
                        "search_modes": item.plan.search_modes,
                        "rerankers": item.plan.rerankers,
                        "generators": item.plan.generators,
                        "context_k": item.plan.context_k,
                        "diversify": item.plan.diversify,
                    }
                    if item.plan
                    else None
                ),
            }
            for item in items
        ],
    }


async def run_examination(
    factory: async_sessionmaker[AsyncSession],
    rag: Rag,
    catalog: Catalog,
    examination_id: int,
    progress: JobProgress,
) -> dict[str, Any]:
    """Examine every question of an examination and store one case per question."""
    async with factory() as db:
        examination = await db.get(models.Examination, examination_id)
        if examination is None:
            raise rb.ExperimentError(f"examination {examination_id} does not exist")
        library = await load_library(db)
        wanted = list(examination.question_ids)
        documents = {document.id: document.text for document in library.documents}
        questions = [q for q in (library.question(qid) for qid in wanted) if q is not None]
        if not questions:
            raise rb.ExperimentError("none of the examination's questions is in the question set")
        await db.execute(
            delete(models.ExaminationCase).where(
                models.ExaminationCase.examination_id == examination_id
            )
        )
        await db.commit()
        client: httpx.AsyncClient | None = None
        target: Target
        if examination.target_kind == "own":
            assert examination.configuration is not None
            spec = spec_of(examination.configuration)
            progress.note("Checking the index")
            await rag.pipeline(spec, library.collection).index(library.documents)
            target = OwnTarget(rag, spec, library.collection)
        else:
            assert examination.external_system is not None
            client = httpx.AsyncClient()
            target = ExternalTarget(
                ExternalSpec.model_validate(examination.external_system.spec), client
            )
    judge = rag.judge()
    limit = asyncio.Semaphore(CONCURRENCY)
    progress.start(f"Examining {len(questions)} questions", len(questions))

    async def one(question: rb.Question) -> None:
        async with limit:
            gold = gold_of(question, documents[question.document_id])
            try:
                outcome: str
                outcome, data = await examine_question(target, judge, question, gold)
            except (rb.ProviderError, ConnectorError) as error:
                logger.warning("question %s failed: %s", question.id, error)
                outcome, data = ERROR, {"question": question.text, "error": str(error)}
            async with factory() as session:
                session.add(
                    models.ExaminationCase(
                        examination_id=examination_id,
                        question_id=question.id,
                        outcome=str(outcome),
                        data=data,
                    )
                )
                await session.commit()
            progress.advance()

    try:
        await asyncio.gather(*(one(question) for question in questions))
    finally:
        if client is not None:
            await client.aclose()
    async with factory() as db:
        examination = await db.get(models.Examination, examination_id)
        assert examination is not None
        examination.summary = await build_summary(db, examination, catalog)
        await db.commit()
        return {
            "examination_id": examination_id,
            "correct_rate": examination.summary["correct_rate"],
            "paid_usd": examination.summary["paid_usd"],
        }
