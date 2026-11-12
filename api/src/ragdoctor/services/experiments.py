"""Experiments on the library, run by the engine's three-stage runner."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import polars as pl
import ragbench as rb
from pydantic import BaseModel, ConfigDict, Field
from ragbench.components.postgres import shared_database
from ragbench.experiment.results import ResultsRepository
from ragbench.experiment.stats import bootstrap_mean, stratified_sample
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ragdoctor import models
from ragdoctor.catalog import Catalog, judge_component
from ragdoctor.doctor.compare import gain_over
from ragdoctor.jobs.queue import JobProgress
from ragdoctor.library import Library, load_library, write_snapshot
from ragdoctor.rag import Rag
from ragdoctor.settings import Settings

MAX_CONTEXT = 10


class ExperimentRequest(BaseModel):
    """What to compare, as catalogue option ids."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Lab experiment", max_length=200)
    purpose: str = Field(default="", max_length=2000)
    chunkers: list[str] = Field(min_length=1)
    embedders: list[str] = Field(min_length=1)
    search_modes: list[str] = Field(min_length=1)
    rerankers: list[str] = Field(default_factory=list)
    generators: list[str] = Field(min_length=1)
    context_k: int = Field(default=5, ge=1, le=MAX_CONTEXT)
    questions: int | None = Field(default=40, ge=5, le=1000)
    question_ids: list[str] | None = None
    top_configs: int = Field(default=3, ge=1, le=5)
    diversify: Literal["none", "chunker"] = "chunker"


def choose_questions(library: Library, count: int | None, seed: int = 42) -> list[str]:
    """Return ``count`` question ids spread over sources in proportion (all if ``None``)."""
    by_source: dict[str, list[rb.Question]] = {}
    for question in library.questions:
        by_source.setdefault(question.source, []).append(question)
    if count is None:
        return [q.id for q in library.questions]
    return [q.id for q in stratified_sample(by_source, count, seed=seed)]


def build_config(
    request: ExperimentRequest,
    *,
    snapshot: Path,
    questions: int,
    catalog: Catalog,
    settings: Settings,
    name: str = "lab",
) -> rb.ExperimentConfig:
    """Translate a request into the engine's experiment configuration.

    Raises:
        ValueError: If an option id is unknown or the combination is invalid.
    """

    def components(kind: str, ids: list[str]) -> list[dict[str, Any]]:
        return [catalog.option(kind, option_id).component.model_dump() for option_id in ids]

    modes = [mode for mode in request.search_modes if mode in catalog.search_modes]
    if not modes:
        raise ValueError("choose at least one offered search mode")
    data = {
        "name": name,
        "seed": 42,
        "data_dir": str(settings.data_dir),
        "corpus": {"name": "library_snapshot", "params": {"path": str(snapshot)}},
        "database": {"url": settings.database_url, "schema": settings.engine_schema},
        "retrieval": {
            "chunkers": components("chunkers", request.chunkers),
            "embedders": components("embedders", request.embedders),
            "search_modes": modes,
            "top_k": MAX_CONTEXT,
        },
        "rerank": {
            "rerankers": components("rerankers", request.rerankers),
            "top_configs": request.top_configs,
            "diversify": request.diversify,
            "candidates": 20,
        },
        "answer": {
            "generators": components("generators", request.generators),
            "judge": judge_component(settings.judge_model).model_dump(),
            "top_configs": request.top_configs,
            "diversify": request.diversify,
            "questions": questions,
            "context_k": request.context_k,
            "validation_sample": 0,
        },
    }
    try:
        return rb.ExperimentConfig.model_validate(data)
    except Exception as error:  # pydantic's error lists every offending field
        raise ValueError(str(error)) from error


def _plain(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _rows(
    frame: pl.DataFrame, columns: list[str], limit: int | None = None
) -> list[dict[str, Any]]:
    if not frame.height:
        return []
    present = [column for column in columns if column in frame.columns]
    rows = frame.select(present).to_dicts()
    rows = rows[:limit] if limit else rows
    return [{key: _plain(value) for key, value in row.items()} for row in rows]


async def _baseline(
    factory: async_sessionmaker[AsyncSession],
    examination_id: int,
    runtime: rb.Runtime,
    run_id: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Score the examined configuration like the experiment's rows, and each row against it.

    The examination already judged the current configuration on these questions with the
    same judge and rubric, so its correctness scores are the baseline; each candidate's gain
    is paired by question.
    """
    async with factory() as db:
        examination = await db.get(models.Examination, examination_id)
        cases = (
            await db.scalars(
                select(models.ExaminationCase).where(
                    models.ExaminationCase.examination_id == examination_id
                )
            )
        ).all()
    if examination is None:
        return None
    current = {
        case.question_id: float(case.data["scores"]["correctness"]) / 2
        for case in cases
        if case.outcome not in ("error", "wrong_gold") and case.data.get("scores")
    }
    scored: dict[str, dict[str, float]] = {}
    for row in await runtime.results.results(run_id, 3):
        scores = row.data.get("scores")
        if isinstance(scores, dict) and "correctness" in scores:
            scored.setdefault(row.config_key, {})[row.question_id] = (
                float(scores["correctness"]) / 2
            )
    for answer in answers:
        gain = gain_over(current, scored.get(answer["config_key"], {}))
        answer["gain"] = _plain(gain.difference.mean) if gain else None
        answer["gain_low"] = _plain(gain.difference.low) if gain else None
        answer["gain_high"] = _plain(gain.difference.high) if gain else None
        answer["gain_significant"] = bool(gain and gain.difference.excludes_zero)
    if not current:
        return None
    interval = bootstrap_mean(list(current.values()), seed=0)
    return {
        "examination_id": examination_id,
        "configuration": str(examination.target.get("display", "")),
        "correctness": _plain(interval.mean),
        "correctness_low": _plain(interval.low),
        "correctness_high": _plain(interval.high),
        "questions": len(current),
    }


async def run_experiment_job(
    factory: async_sessionmaker[AsyncSession],
    rag: Rag,
    catalog: Catalog,
    settings: Settings,
    experiment_id: int,
    progress: JobProgress,
) -> dict[str, Any]:
    """Run an experiment with the engine and store its leaderboards and report."""
    async with factory() as db:
        experiment = await db.get(models.Experiment, experiment_id)
        if experiment is None:
            raise rb.ExperimentError(f"experiment {experiment_id} does not exist")
        request = ExperimentRequest.model_validate(experiment.config)
        examination_id = experiment.examination_id
        library = await load_library(db)
    ids = request.question_ids or choose_questions(library, request.questions)
    wanted = set(ids)
    subset = Library(
        documents=library.documents,
        questions=tuple(q for q in library.questions if q.id in wanted),
    )
    if not subset.questions:
        raise rb.ExperimentError("the experiment has no gold question to run on")
    snapshot = write_snapshot(subset, settings.data_dir / "snapshots")
    config = build_config(
        request,
        snapshot=snapshot,
        questions=len(subset.questions),
        catalog=catalog,
        settings=settings,
    )
    resources = rag.session.resources
    runtime = rb.Runtime(
        config=config,
        resources=resources,
        store=rag.session.store,
        results=ResultsRepository(
            shared_database(resources, settings.database_url, settings.engine_schema)
        ),
    )
    async with factory() as db:
        experiment = await db.get(models.Experiment, experiment_id)
        assert experiment is not None
        experiment.run_id = config.run_id
        await db.commit()
    summary = await rb.run_experiment(runtime, progress)
    progress.note("Writing the report")
    report = await rb.Report.load(runtime.results, summary.run_id)
    page = report.write(settings.data_dir / "reports" / summary.run_id)
    specs = {
        config.config_key: config.spec
        for config in await runtime.results.stage_configs(summary.run_id)
    }
    answers = _rows(
        report.answers,
        [
            "config_key",
            "configuration",
            "retrieval",
            "generator",
            "questions",
            "correctness",
            "correctness_low",
            "correctness_high",
            "faithfulness",
            "citation",
            "gold_in_context",
            "cost_per_1k_answers_usd",
            "latency_p50_s",
            "tied_with_best",
            "gap_to_best",
        ],
    )
    for row in answers:
        row["spec"] = specs.get(row["config_key"])
    baseline = None
    if examination_id is not None:
        baseline = await _baseline(factory, examination_id, runtime, summary.run_id, answers)
    primary = report.primary_metric
    retrieval_columns = [
        "config_key",
        "configuration",
        "chunker",
        "embedder",
        "search_mode",
        "reranker",
        primary,
        "primary_low",
        "primary_high",
        "recall@5",
        "recall@10",
        "cost_per_1k_queries_usd",
    ]
    recommendation = report.recommendation
    result = {
        "run_id": summary.run_id,
        "questions": len(subset.questions),
        "primary_metric": primary,
        "answers": answers,
        "retrieval": _rows(report.retrieval, retrieval_columns, limit=12),
        "reranking": _rows(report.reranking, [*retrieval_columns, "gain", "significant"]),
        "recommendation": (
            {
                "config_key": recommendation.config_key,
                "display": recommendation.display,
                "stage": recommendation.stage,
                "reason": recommendation.reason,
                "spec": specs.get(recommendation.config_key),
            }
            if recommendation
            else None
        ),
        "baseline": baseline,
        "paid_usd": summary.paid_usd,
        "failed": summary.failed,
        "seconds": summary.seconds,
        "report_path": str(page),
    }
    async with factory() as db:
        experiment = await db.get(models.Experiment, experiment_id)
        assert experiment is not None
        experiment.summary = result
        await db.commit()
    return {"experiment_id": experiment_id, "run_id": summary.run_id, "paid_usd": summary.paid_usd}
