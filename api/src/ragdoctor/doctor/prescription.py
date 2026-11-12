"""From the failure breakdown to candidate fixes, and the experiment that measures them.

The doctor does not recommend a fix from a rule of thumb. For each failure type it names the
part of the pipeline that failed and the candidate changes there; for this application's own
configuration it also plans an experiment that varies exactly that part, so the choice is made
by measurement on the corpus at hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ragdoctor.catalog import Catalog, Selection
from ragdoctor.doctor.diagnosis import Outcome, Summary

STAGES = {
    Outcome.NOT_RETRIEVED: "retrieval",
    Outcome.RANKED_LOW: "ranking",
    Outcome.IGNORED: "generation",
    Outcome.UNSUPPORTED: "generation",
    Outcome.WRONG_ANSWER: "unknown",
}

CANDIDATES = {
    Outcome.NOT_RETRIEVED: ["chunking", "embedding model", "search mode (dense, hybrid, lexical)"],
    Outcome.RANKED_LOW: ["a reranker", "more passages in the context"],
    Outcome.IGNORED: ["generator model", "answer prompt"],
    Outcome.UNSUPPORTED: ["generator model", "answer prompt", "citation check"],
    Outcome.WRONG_ANSWER: ["return the retrieved passages, so the failing stage can be located"],
}

MAX_CONTEXT = 10  # the experiment retrieves 10 passages per question


@dataclass(frozen=True, slots=True)
class Plan:
    """An experiment, as catalogue option ids.

    Attributes:
        focus: The pipeline part it varies: ``retrieval``, ``ranking`` or ``generation``.
        description: One sentence on what is compared, for the screen.
        chunkers, embedders, search_modes: The retrieval grid (stage 1 of the engine's runner).
        rerankers: Rerankers tried on the best retrieval configurations (stage 2).
        generators: Generators tried on the best configurations, scored by the judge (stage 3).
        context_k: Passages given to the generator in stage 3.
    """

    focus: str
    description: str
    chunkers: list[str]
    embedders: list[str]
    search_modes: list[str]
    rerankers: list[str]
    generators: list[str]
    context_k: int


@dataclass(slots=True)
class Item:
    """One line of the prescription.

    Attributes:
        outcome: The failure type.
        count: Questions with this outcome.
        share: ``count`` over the evaluated questions.
        stage: Pipeline part that failed.
        candidates: Changes worth measuring there.
        plan: The experiment that measures them; ``None`` for external systems, when the
            configuration is not in the catalogue, or when an earlier item has the same plan.
        same_plan_as: The earlier item whose experiment also covers this one.
    """

    outcome: Outcome
    count: int
    share: float
    stage: str
    candidates: list[str]
    plan: Plan | None = None
    same_plan_as: Outcome | None = None
    notes: list[str] = field(default_factory=list)


def _cheap_rerankers(catalog: Catalog) -> list[str]:
    return [option.id for option in catalog.rerankers if not option.expensive]


def _retrieval(current: Selection, catalog: Catalog) -> tuple[list[str], list[str], list[str]]:
    embedder = current.embedder or catalog.embedders[0].id
    return [current.chunker], [embedder], [current.search_mode]


def plan_for(outcome: Outcome, current: Selection, catalog: Catalog) -> Plan | None:
    """Return the experiment that measures the candidate fixes of ``outcome``."""
    generator = current.generator or catalog.generators[0].id
    reranker = [current.reranker] if current.reranker else _cheap_rerankers(catalog)[:1]
    if outcome is Outcome.NOT_RETRIEVED:
        return Plan(
            focus="retrieval",
            description=(
                "Compares every offered chunker, embedding model and search mode on these "
                f"questions, then answers with {generator} on the best of them."
            ),
            chunkers=[option.id for option in catalog.chunkers],
            embedders=[option.id for option in catalog.embedders],
            search_modes=list(catalog.search_modes),
            rerankers=reranker,
            generators=[generator],
            context_k=current.top_k,
        )
    if outcome is Outcome.RANKED_LOW:
        chunkers, embedders, modes = _retrieval(current, catalog)
        context_k = min(MAX_CONTEXT, current.top_k + 3)
        return Plan(
            focus="ranking",
            description=(
                "Keeps the current retrieval, tries the offered rerankers and gives the "
                f"generator {context_k} passages instead of {current.top_k}."
            ),
            chunkers=chunkers,
            embedders=embedders,
            search_modes=modes,
            rerankers=_cheap_rerankers(catalog),
            generators=[generator],
            context_k=context_k,
        )
    if outcome in (Outcome.IGNORED, Outcome.UNSUPPORTED):
        chunkers, embedders, modes = _retrieval(current, catalog)
        return Plan(
            focus="generation",
            description=(
                "Keeps the current retrieval and compares every offered generator on the same "
                "passages."
            ),
            chunkers=chunkers,
            embedders=embedders,
            search_modes=modes,
            rerankers=[current.reranker] if current.reranker else [],
            generators=[option.id for option in catalog.generators],
            context_k=current.top_k,
        )
    return None


def prescribe(
    summary: Summary, *, current: Selection | None, catalog: Catalog, external: bool
) -> list[Item]:
    """Return one item per failure type that occurred, largest first."""
    items: list[Item] = []
    planned: dict[str, Outcome] = {}
    for outcome, count in summary.failures:
        item = Item(
            outcome=outcome,
            count=count,
            share=count / summary.evaluated if summary.evaluated else 0.0,
            stage=STAGES[outcome],
            candidates=list(CANDIDATES[outcome]),
        )
        if external and outcome is Outcome.NOT_RETRIEVED:
            # Without the candidates, a passage cut from the context looks the same as one
            # that was never found.
            item.candidates += ["a reranker", "more passages in the context"]
            item.notes.append(
                "The system does not return its retrieval candidates, so a gold passage that was "
                "found and then ranked out of the context cannot be told apart from one that "
                "was never found."
            )
        if not external and current is not None:
            plan = plan_for(outcome, current, catalog)
            if plan is not None and plan.focus in planned:
                item.same_plan_as = planned[plan.focus]
            elif plan is not None:
                item.plan = plan
                planned[plan.focus] = outcome
        items.append(item)
    return items
