"""The doctor's decision rule: one outcome per question, from what was observed."""

import pytest

from ragdoctor.doctor.diagnosis import Evidence, Outcome, diagnose, summarise


def evidence(**overrides: object) -> Evidence:
    base = {
        "correctness": 0,
        "faithfulness": 2,
        "gold_in_candidates": True,
        "gold_in_context": True,
    }
    return Evidence(**{**base, **overrides})  # type: ignore[arg-type]


def test_right_and_supported_answer_is_correct() -> None:
    assert diagnose(evidence(correctness=2, faithfulness=2)) is Outcome.CORRECT


def test_right_answer_with_one_unsupported_detail_still_counts_as_correct() -> None:
    assert diagnose(evidence(correctness=2, faithfulness=1)) is Outcome.CORRECT


def test_right_answer_whose_main_claim_is_not_in_the_context_is_unsupported() -> None:
    assert diagnose(evidence(correctness=2, faithfulness=0)) is Outcome.UNSUPPORTED


def test_gold_missing_from_the_candidates_is_not_retrieved() -> None:
    found = diagnose(evidence(gold_in_candidates=False, gold_in_context=False))
    assert found is Outcome.NOT_RETRIEVED


def test_gold_among_candidates_but_outside_the_context_is_ranked_low() -> None:
    found = diagnose(evidence(gold_in_candidates=True, gold_in_context=False))
    assert found is Outcome.RANKED_LOW


def test_retrieval_failure_wins_over_an_unsupported_answer() -> None:
    # The generator invented something, but it was never given the evidence: fix retrieval first.
    found = diagnose(evidence(faithfulness=0, gold_in_candidates=False, gold_in_context=False))
    assert found is Outcome.NOT_RETRIEVED


def test_gold_in_context_and_faithful_but_wrong_is_ignored() -> None:
    assert diagnose(evidence(correctness=0, faithfulness=2)) is Outcome.IGNORED


def test_partially_right_answer_with_gold_in_context_is_ignored() -> None:
    assert diagnose(evidence(correctness=1, faithfulness=1)) is Outcome.IGNORED


def test_gold_in_context_and_claims_outside_it_is_unsupported() -> None:
    assert diagnose(evidence(correctness=0, faithfulness=0)) is Outcome.UNSUPPORTED


def test_reviewer_marking_the_question_bad_overrides_everything() -> None:
    assert diagnose(evidence(correctness=2, wrong_gold=True)) is Outcome.WRONG_GOLD
    assert diagnose(evidence(correctness=0, wrong_gold=True)) is Outcome.WRONG_GOLD


def test_system_without_candidates_cannot_be_ranked_low() -> None:
    # An external system that returns only its final passages: a missing gold passage is
    # reported as not retrieved, because nothing shows it was found and then dropped.
    found = diagnose(evidence(gold_in_candidates=None, gold_in_context=False))
    assert found is Outcome.NOT_RETRIEVED


def test_system_without_passages_gets_answer_level_diagnosis_only() -> None:
    right = evidence(correctness=2, faithfulness=0, gold_in_candidates=None, gold_in_context=None)
    wrong = evidence(correctness=1, faithfulness=0, gold_in_candidates=None, gold_in_context=None)
    assert diagnose(right) is Outcome.CORRECT
    assert diagnose(wrong) is Outcome.WRONG_ANSWER


@pytest.mark.parametrize("score", [-1, 3])
def test_scores_outside_the_rubric_are_rejected(score: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 2"):
        evidence(correctness=score)


def test_summary_counts_outcomes_and_excludes_wrong_gold_from_the_rate() -> None:
    outcomes = [
        Outcome.CORRECT,
        Outcome.CORRECT,
        Outcome.CORRECT,
        Outcome.NOT_RETRIEVED,
        Outcome.WRONG_GOLD,
    ]
    summary = summarise(outcomes)
    assert summary.total == 5
    assert summary.evaluated == 4
    assert summary.counts[Outcome.CORRECT] == 3
    assert summary.counts[Outcome.IGNORED] == 0
    assert summary.correct_rate == pytest.approx(0.75)
    assert summary.failures == [(Outcome.NOT_RETRIEVED, 1)]


def test_summary_orders_failures_by_size_then_by_pipeline_order() -> None:
    outcomes = [
        Outcome.UNSUPPORTED,
        Outcome.IGNORED,
        Outcome.IGNORED,
        Outcome.NOT_RETRIEVED,
        Outcome.RANKED_LOW,
        Outcome.RANKED_LOW,
    ]
    assert summarise(outcomes).failures == [
        (Outcome.RANKED_LOW, 2),
        (Outcome.IGNORED, 2),
        (Outcome.NOT_RETRIEVED, 1),
        (Outcome.UNSUPPORTED, 1),
    ]


def test_summary_of_nothing_has_no_rate() -> None:
    summary = summarise([])
    assert summary.evaluated == 0
    assert summary.correct_rate is None
