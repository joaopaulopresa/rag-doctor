"""Experiments on the library, run by the engine's three-stage runner."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import polars as pl
import ragbench as rb
from pydantic import BaseModel, ConfigDict, Field
from ragbench.components.postgres import shared_database
from ragbench.experiment.results import ResultsRepository
from ragbench.experiment.stats import stratified_sample
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ragdoctor import models
from ragdoctor.catalog import Catalog, judge_component
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
            "diversify": "chunker",
            "candidates": 20,
        },
        "answer": {
            "generators": components("generators", request.generators),
            "judge": judge_component(settings.judge_model).model_dump(),
            "top_configs": request.top_configs,
            "diversify": "chunker",
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
