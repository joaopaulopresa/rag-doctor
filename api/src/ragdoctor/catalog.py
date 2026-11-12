"""The options the admin may combine into a pipeline configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from ragbench import ComponentConfig, PipelineConfig

from ragdoctor.settings import get_settings

SearchMode = Literal["dense", "lexical", "hybrid"]


class Option(BaseModel):
    """One selectable component."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    component: ComponentConfig
    expensive: bool = False


class Selection(BaseModel):
    """A pipeline described by option ids, as the screens send it."""

    model_config = ConfigDict(extra="forbid")

    chunker: str
    embedder: str | None = None
    search_mode: SearchMode = "dense"
    reranker: str | None = None
    generator: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    candidates: int = Field(default=20, ge=1, le=50)


class Catalog(BaseModel):
    """Everything in ``catalog.yaml``."""

    model_config = ConfigDict(extra="forbid")

    chunkers: list[Option]
    embedders: list[Option]
    search_modes: list[SearchMode]
    rerankers: list[Option]
    generators: list[Option]
    initial: Selection

    def option(self, kind: str, option_id: str) -> Option:
        """Return the option ``option_id`` of ``kind`` (``chunkers``, ``embedders``, ...).

        Raises:
            ValueError: If the catalogue has no such option.
        """
        for option in getattr(self, kind):
            if option.id == option_id:
                return option
        allowed = ", ".join(option.id for option in getattr(self, kind))
        raise ValueError(f"unknown {kind[:-1]} {option_id!r}; allowed: {allowed}")

    def pipeline(self, selection: Selection) -> PipelineConfig:
        """Turn option ids into the engine's ``PipelineConfig``.

        Raises:
            ValueError: If an id is unknown or the combination is invalid.
        """
        if selection.search_mode not in self.search_modes:
            raise ValueError(f"search mode {selection.search_mode!r} is not offered")
        embedder = selection.embedder
        if selection.search_mode == "lexical":
            embedder = None
        return PipelineConfig(
            chunker=self.option("chunkers", selection.chunker).component,
            embedder=self.option("embedders", embedder).component if embedder else None,
            search_mode=selection.search_mode,
            reranker=(
                self.option("rerankers", selection.reranker).component
                if selection.reranker
                else None
            ),
            generator=(
                self.option("generators", selection.generator).component
                if selection.generator
                else None
            ),
            top_k=selection.top_k,
            candidates=max(selection.candidates, selection.top_k),
        )

    def selection(self, spec: PipelineConfig) -> Selection | None:
        """Return the option ids behind ``spec``, or ``None`` if a part is not in the catalogue."""

        def find(kind: str, component: ComponentConfig | None) -> str | None:
            if component is None:
                return None
            for option in getattr(self, kind):
                if option.component.key == component.key:
                    return str(option.id)
            raise LookupError(kind)

        try:
            chunker = find("chunkers", spec.chunker)
            assert chunker is not None
            return Selection(
                chunker=chunker,
                embedder=find("embedders", spec.embedder),
                search_mode=spec.search_mode,
                reranker=find("rerankers", spec.reranker),
                generator=find("generators", spec.generator),
                top_k=spec.top_k,
                candidates=spec.candidates,
            )
        except LookupError:
            return None

    def public(self) -> dict[str, Any]:
        """Return what the pickers need: ids, labels and the model behind each option."""

        def rows(options: list[Option]) -> list[dict[str, Any]]:
            return [
                {
                    "id": option.id,
                    "label": option.label,
                    "model": option.component.params.get("model"),
                    "expensive": option.expensive,
                }
                for option in options
            ]

        return {
            "chunkers": rows(self.chunkers),
            "embedders": rows(self.embedders),
            "search_modes": self.search_modes,
            "rerankers": rows(self.rerankers),
            "generators": rows(self.generators),
            "initial": self.initial.model_dump(),
        }


def load_catalog(path: Path) -> Catalog:
    """Read and validate a catalogue file."""
    return Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def get_catalog() -> Catalog:
    """Return the catalogue of this process."""
    return load_catalog(get_settings().catalog_path)


def judge_component(model: str) -> ComponentConfig:
    """Return the judge: an LLM applying the engine's rubric, with reasoning switched off."""
    return ComponentConfig(
        name="llm",
        params={
            "generator": {
                "name": "openrouter",
                "params": {
                    "model": model,
                    "temperature": 0,
                    "max_tokens": 400,
                    "extra_body": {
                        "reasoning": {"enabled": False},
                        "response_format": {"type": "json_object"},
                    },
                },
            }
        },
    )


def question_writer_component(model: str) -> ComponentConfig:
    """Return the generator that drafts candidate questions (the cheapest model)."""
    return ComponentConfig(
        name="openrouter",
        params={"model": model, "temperature": 0.3, "max_tokens": 300},
    )


def describe(spec: PipelineConfig) -> dict[str, Any]:
    """Return a configuration as labelled parts for display."""

    def part(component: ComponentConfig | None) -> dict[str, Any] | None:
        if component is None:
            return None
        return {
            "display": component.display,
            "name": component.name,
            "model": component.params.get("model"),
        }

    return {
        "key": spec.key,
        "display": spec.display,
        "chunker": part(spec.chunker),
        "embedder": part(spec.embedder),
        "search_mode": spec.search_mode,
        "reranker": part(spec.reranker),
        "generator": part(spec.generator),
        "top_k": spec.top_k,
        "candidates": spec.candidates,
    }
