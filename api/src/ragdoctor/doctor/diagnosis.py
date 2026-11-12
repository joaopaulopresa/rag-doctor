"""The decision rule of the doctor: one outcome per question.

Pure functions. Scores come from the judge (0, 1 or 2 per criterion, see the engine's rubric);
they are judge scores and have not been validated against human labels.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    """What happened to one question. Failures are listed in pipeline order."""

    CORRECT = "correct"
    NOT_RETRIEVED = "not_retrieved"
    RANKED_LOW = "ranked_low"
    IGNORED = "ignored"
    UNSUPPORTED = "unsupported"
    WRONG_ANSWER = "wrong_answer"
    WRONG_GOLD = "wrong_gold"


#: Failure outcomes in the order the pipeline produces them.
FAILURES = (
    Outcome.NOT_RETRIEVED,
    Outcome.RANKED_LOW,
    Outcome.IGNORED,
    Outcome.UNSUPPORTED,
    Outcome.WRONG_ANSWER,
)

LABELS = {
    Outcome.CORRECT: "Correct",
    Outcome.NOT_RETRIEVED: "Not retrieved",
    Outcome.RANKED_LOW: "Retrieved, ranked low",
    Outcome.IGNORED: "In context, ignored",
    Outcome.UNSUPPORTED: "Unsupported",
    Outcome.WRONG_ANSWER: "Wrong answer (no passages to inspect)",
    Outcome.WRONG_GOLD: "Wrong gold",
}

MEANINGS = {
    Outcome.CORRECT: "The answer matches the gold evidence and is supported by the passages.",
    Outcome.NOT_RETRIEVED: "The gold passage was not among the retrieved candidates.",
    Outcome.RANKED_LOW: "The gold passage was found but fell out of the context given to the "
    "generator.",
    Outcome.IGNORED: "The gold passage was in the context and the answer still missed it.",
    Outcome.UNSUPPORTED: "The main claim of the answer is not supported by the context.",
    Outcome.WRONG_ANSWER: "The answer does not match the gold evidence; the system returned no "
    "passages, so the cause cannot be located.",
    Outcome.WRONG_GOLD: "A reviewer marked the question or its gold evidence as wrong.",
}


@dataclass(frozen=True, slots=True)
class Evidence:
    """What was observed for one question.

    Attributes:
        correctness: Judge score, 0 to 2: does the answer state what the gold evidence states?
        faithfulness: Judge score, 0 to 2: is the answer supported by the passages it was given?
        gold_in_candidates: Whether a gold passage was among the retrieved candidates, before
            any cut to the context size. ``None`` when the system does not expose candidates.
        gold_in_context: Whether a gold passage was in the context given to the generator.
            ``None`` when the system returns no passages at all.
        wrong_gold: A reviewer marked the question itself as bad.
    """

    correctness: int
    faithfulness: int
    gold_in_candidates: bool | None
    gold_in_context: bool | None
    wrong_gold: bool = False

    def __post_init__(self) -> None:
        for name in ("correctness", "faithfulness"):
            if not 0 <= getattr(self, name) <= 2:
                raise ValueError(f"{name} must be between 0 and 2")


def diagnose(evidence: Evidence) -> Outcome:
    """Assign the outcome of one question.

    A fully correct answer (correctness 2) whose main claim is supported (faithfulness at least
    1) is correct. Otherwise the first stage that failed is blamed, in pipeline order: the
    evidence was not retrieved, was retrieved but cut from the context, or was in the context
    and the generator either ignored it or wrote something the context does not support.
    """
    if evidence.wrong_gold:
        return Outcome.WRONG_GOLD
    right = evidence.correctness == 2
    if evidence.gold_in_context is None:
        return Outcome.CORRECT if right else Outcome.WRONG_ANSWER
    if right:
        return Outcome.CORRECT if evidence.faithfulness >= 1 else Outcome.UNSUPPORTED
    if not evidence.gold_in_context:
        return Outcome.RANKED_LOW if evidence.gold_in_candidates else Outcome.NOT_RETRIEVED
    return Outcome.UNSUPPORTED if evidence.faithfulness == 0 else Outcome.IGNORED


@dataclass(frozen=True, slots=True)
class Summary:
    """Totals of an examination.

    Attributes:
        total: Questions examined.
        evaluated: Questions that count: ``total`` minus those marked wrong gold.
        counts: Number of questions per outcome (every outcome is present).
        correct_rate: Share of evaluated questions that are correct; ``None`` if none count.
        failures: Failure outcomes that occurred with their counts, largest first; ties keep
            pipeline order.
    """

    total: int
    evaluated: int
    counts: dict[Outcome, int]
    correct_rate: float | None
    failures: list[tuple[Outcome, int]]


def summarise(outcomes: Iterable[Outcome]) -> Summary:
    """Count outcomes and rank the failures."""
    counts = dict.fromkeys(Outcome, 0)
    for outcome in outcomes:
        counts[outcome] += 1
    total = sum(counts.values())
    evaluated = total - counts[Outcome.WRONG_GOLD]
    failures = sorted(
        ((outcome, counts[outcome]) for outcome in FAILURES if counts[outcome]),
        key=lambda item: -item[1],
    )
    return Summary(
        total=total,
        evaluated=evaluated,
        counts=counts,
        correct_rate=counts[Outcome.CORRECT] / evaluated if evaluated else None,
        failures=failures,
    )
