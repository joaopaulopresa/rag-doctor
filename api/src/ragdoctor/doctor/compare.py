"""Before/after comparison of two examinations over the same questions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ragbench.experiment.stats import Interval, bootstrap_mean, paired_bootstrap

from ragdoctor.doctor.diagnosis import Outcome

CHANGES = ("fixed", "broken", "still_wrong", "still_correct")


@dataclass(frozen=True, slots=True)
class Movement:
    """How one question moved between the two examinations."""

    question_id: str
    before: Outcome
    after: Outcome
    change: str


@dataclass(frozen=True, slots=True)
class Comparison:
    """The result of `compare`.

    Attributes:
        movements: One entry per compared question, ordered by question id.
        counts: Questions per change (``fixed``, ``broken``, ``still_wrong``, ``still_correct``).
        before: Correct rate before, with a bootstrap confidence interval.
        after: Correct rate after, with a bootstrap confidence interval.
        difference: ``after - before`` with a paired bootstrap interval.
        questions: Questions compared.
        excluded: Questions of either side left out (missing on the other side, marked wrong
            gold, or failed).
    """

    movements: list[Movement]
    counts: dict[str, int]
    before: Interval
    after: Interval
    difference: Interval
    questions: int
    excluded: int


def _usable(value: object) -> bool:
    return isinstance(value, Outcome) and value is not Outcome.WRONG_GOLD


def compare(
    before: Mapping[str, Outcome | str],
    after: Mapping[str, Outcome | str],
    *,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Comparison:
    """Compare two examinations question by question.

    Args:
        before: Outcome per question id of the first examination (``"error"`` for a question
            that could not be examined).
        after: The same for the second examination.

    Raises:
        ValueError: If the two have no usable question in common.
    """
    common = sorted(
        question
        for question in set(before) & set(after)
        if _usable(before[question]) and _usable(after[question])
    )
    if not common:
        raise ValueError("the two examinations have no question in common to compare")
    movements = []
    for question in common:
        old, new = Outcome(before[question]), Outcome(after[question])
        was, now = old is Outcome.CORRECT, new is Outcome.CORRECT
        change = {
            (False, True): "fixed",
            (True, False): "broken",
            (False, False): "still_wrong",
            (True, True): "still_correct",
        }[(was, now)]
        movements.append(Movement(question, old, new, change))
    first = [1.0 if m.before is Outcome.CORRECT else 0.0 for m in movements]
    second = [1.0 if m.after is Outcome.CORRECT else 0.0 for m in movements]
    options = {"samples": samples, "confidence": confidence, "seed": seed}
    return Comparison(
        movements=movements,
        counts={change: sum(m.change == change for m in movements) for change in CHANGES},
        before=bootstrap_mean(first, **options),
        after=bootstrap_mean(second, **options),
        difference=paired_bootstrap(second, first, **options),
        questions=len(common),
        excluded=len(set(before) | set(after)) - len(common),
    )


@dataclass(frozen=True, slots=True)
class Gain:
    """A candidate configuration measured against the current one on the same questions.

    Attributes:
        questions: Questions both were scored on.
        baseline: Mean score of the current configuration on those questions.
        candidate: Mean score of the candidate on those questions.
        difference: ``candidate - baseline`` with a paired bootstrap interval.
    """

    questions: int
    baseline: float
    candidate: float
    difference: Interval


def gain_over(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    *,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Gain | None:
    """Return the paired gain of ``candidate`` over ``baseline`` (scores by question id).

    Returns ``None`` when the two share no question.
    """
    common = sorted(set(baseline) & set(candidate))
    if not common:
        return None
    first = [candidate[q] for q in common]
    second = [baseline[q] for q in common]
    return Gain(
        questions=len(common),
        baseline=sum(second) / len(common),
        candidate=sum(first) / len(common),
        difference=paired_bootstrap(
            first, second, samples=samples, confidence=confidence, seed=seed
        ),
    )
