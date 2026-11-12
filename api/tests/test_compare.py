"""Before/after: per-question movement and totals with confidence intervals."""

import pytest

from ragdoctor.doctor.compare import compare
from ragdoctor.doctor.diagnosis import Outcome

C, NR, IG, WG = Outcome.CORRECT, Outcome.NOT_RETRIEVED, Outcome.IGNORED, Outcome.WRONG_GOLD


def test_each_question_is_classified_by_how_it_moved() -> None:
    before = {"a": NR, "b": C, "c": IG, "d": C}
    after = {"a": C, "b": NR, "c": NR, "d": C}
    result = compare(before, after)
    moved = {m.question_id: m.change for m in result.movements}
    assert moved == {"a": "fixed", "b": "broken", "c": "still_wrong", "d": "still_correct"}
    assert result.counts == {"fixed": 1, "broken": 1, "still_wrong": 1, "still_correct": 1}


def test_questions_missing_on_one_side_or_marked_wrong_gold_or_failed_are_left_out() -> None:
    before = {"a": C, "b": WG, "c": NR, "d": "error"}
    after = {"a": C, "b": C, "c": C, "d": C, "e": C}
    result = compare(before, after)
    assert [m.question_id for m in result.movements] == ["a", "c"]
    assert result.questions == 2
    assert result.excluded == 3


def test_rates_and_paired_difference_have_intervals() -> None:
    before = {f"q{i}": (C if i < 10 else NR) for i in range(40)}
    after = {f"q{i}": (C if i < 34 else NR) for i in range(40)}
    result = compare(before, after, seed=1)
    assert result.before.mean == pytest.approx(0.25)
    assert result.after.mean == pytest.approx(0.85)
    assert result.difference.mean == pytest.approx(0.60)
    assert result.difference.low > 0
    assert result.before.low <= 0.25 <= result.before.high


def test_comparing_nothing_in_common_is_an_error() -> None:
    with pytest.raises(ValueError, match="no question"):
        compare({"a": C}, {"b": C})
