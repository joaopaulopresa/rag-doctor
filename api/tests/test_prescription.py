"""From the failure breakdown to candidate fixes and the experiment that measures them."""

from pathlib import Path

import pytest

from ragdoctor.catalog import Selection, load_catalog
from ragdoctor.doctor.diagnosis import Outcome, summarise
from ragdoctor.doctor.prescription import prescribe

CATALOG = load_catalog(Path(__file__).resolve().parents[1] / "config" / "catalog.yaml")
FIRST_BUILD = Selection(
    chunker="recursive",
    embedder="bge-m3",
    search_mode="hybrid",
    reranker=None,
    generator="granite-4.2-8b",
    top_k=5,
)
TUNED = Selection(
    chunker="context-header",
    embedder="text-embedding-3-large",
    search_mode="dense",
    reranker="cohere-rerank-5-fast",
    generator="granite-4.2-8b",
    top_k=5,
    candidates=20,
)


def outcomes(**counts: int) -> list[Outcome]:
    return [Outcome(name) for name, count in counts.items() for _ in range(count)]


def test_items_follow_the_failure_ranking_and_carry_their_share() -> None:
    summary = summarise(outcomes(correct=6, not_retrieved=3, ignored=1))
    items = prescribe(summary, current=FIRST_BUILD, catalog=CATALOG, external=False)
    assert [item.outcome for item in items] == [Outcome.NOT_RETRIEVED, Outcome.IGNORED]
    assert items[0].count == 3
    assert items[0].share == pytest.approx(0.3)


def test_not_retrieved_measures_every_offered_chunker_embedder_and_search_mode() -> None:
    summary = summarise(outcomes(not_retrieved=2))
    [item] = prescribe(summary, current=FIRST_BUILD, catalog=CATALOG, external=False)
    plan = item.plan
    assert plan is not None
    assert plan.focus == "retrieval"
    assert set(plan.chunkers) == {option.id for option in CATALOG.chunkers}
    assert set(plan.embedders) == {option.id for option in CATALOG.embedders}
    assert set(plan.search_modes) == set(CATALOG.search_modes)
    # The answer stage keeps the generator, so a change in the score is due to retrieval.
    assert plan.generators == ["granite-4.2-8b"]


def test_no_expensive_reranker_is_ever_put_into_a_plan() -> None:
    summary = summarise(outcomes(not_retrieved=1, ranked_low=1))
    items = prescribe(summary, current=FIRST_BUILD, catalog=CATALOG, external=False)
    expensive = {option.id for option in CATALOG.rerankers if option.expensive}
    for item in items:
        assert item.plan is not None
        assert not expensive & set(item.plan.rerankers)


def test_ranked_low_keeps_retrieval_and_measures_rerankers_with_more_context() -> None:
    summary = summarise(outcomes(ranked_low=2))
    [item] = prescribe(summary, current=FIRST_BUILD, catalog=CATALOG, external=False)
    plan = item.plan
    assert plan is not None
    assert plan.focus == "ranking"
    assert (plan.chunkers, plan.embedders, plan.search_modes) == (
        ["recursive"],
        ["bge-m3"],
        ["hybrid"],
    )
    assert plan.rerankers == ["cohere-rerank-5-fast"]
    assert plan.context_k > FIRST_BUILD.top_k


def test_generator_failures_keep_retrieval_and_compare_every_generator() -> None:
    summary = summarise(outcomes(ignored=3, unsupported=2))
    first, second = prescribe(summary, current=TUNED, catalog=CATALOG, external=False)
    assert first.plan is not None
    assert first.plan.focus == "generation"
    assert first.plan.chunkers == ["context-header"]
    assert first.plan.rerankers == ["cohere-rerank-5-fast"]
    assert set(first.plan.generators) == {option.id for option in CATALOG.generators}
    # Both failures point at the generator: one experiment covers them.
    assert second.plan is None
    assert second.same_plan_as == Outcome.IGNORED


def test_external_systems_get_candidate_fixes_but_no_experiment() -> None:
    summary = summarise(outcomes(not_retrieved=2, wrong_answer=1))
    items = prescribe(summary, current=None, catalog=CATALOG, external=True)
    assert [item.plan for item in items] == [None, None]
    assert items[0].candidates


def test_no_failures_means_no_prescription() -> None:
    assert (
        prescribe(summarise(outcomes(correct=4)), current=TUNED, catalog=CATALOG, external=False)
        == []
    )
