"""The engine session of this process: one cache, one store, pipelines built on demand."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ragbench as rb
from ragbench.core.registries import generators, judges

import ragdoctor.library  # noqa: F401  (registers the snapshot loader)
from ragdoctor.catalog import judge_component, question_writer_component
from ragdoctor.settings import Settings


class Rag:
    """Builds and keeps pipelines on top of one long-lived engine session.

    Args:
        session: The open engine session (cache and chunk store).
        settings: Process settings (model names).
    """

    def __init__(self, session: rb.Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._pipelines: dict[tuple[str, str], rb.Pipeline] = {}
        self._judge: rb.Judge | None = None

    def pipeline(self, spec: rb.PipelineConfig, collection: str) -> rb.Pipeline:
        """Return the pipeline for ``spec`` on ``collection``, building it once."""
        key = (spec.key, collection)
        if key not in self._pipelines:
            self._pipelines[key] = rb.build_pipeline(
                spec,
                resources=self.session.resources,
                store=self.session.store,
                collection=collection,
            )
        return self._pipelines[key]

    def judge(self) -> rb.Judge:
        """Return the judge (an LLM applying the engine's rubric)."""
        if self._judge is None:
            component = judge_component(self.settings.judge_model)
            self._judge = judges.create(component.name, self.session.resources, component.params)
        return self._judge

    def question_writer(self) -> rb.Generator:
        """Return the generator that drafts candidate questions."""
        component = question_writer_component(self.settings.seed_model)
        return generators.create(component.name, self.session.resources, component.params)


@asynccontextmanager
async def open_rag(settings: Settings) -> AsyncIterator[Rag]:
    """Open the engine session for the lifetime of the process."""
    async with rb.open_session(
        settings.database_url,
        schema=settings.engine_schema,
        env=settings.engine_env,
        data_dir=settings.data_dir,
    ) as session:
        yield Rag(session, settings)
