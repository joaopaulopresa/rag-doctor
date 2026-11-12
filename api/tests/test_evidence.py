"""Deciding whether a passage holds the gold evidence, by position or by text."""

from ragdoctor.doctor.evidence import Gold, Passage, first_gold_rank, holds_gold

GOLD = Gold(
    document_id="nda.txt",
    spans=((100, 160),),
    texts=("The Receiving Party shall return all Confidential Information within 30 days.",),
)


def test_passage_with_a_span_overlapping_the_gold_span_holds_it() -> None:
    assert holds_gold(Passage(text="...", document_id="nda.txt", span=(90, 120)), GOLD)


def test_passage_of_another_document_does_not_hold_it_even_at_the_same_offsets() -> None:
    assert not holds_gold(Passage(text="...", document_id="lease.txt", span=(90, 120)), GOLD)


def test_passage_with_a_span_elsewhere_in_the_document_does_not_hold_it() -> None:
    assert not holds_gold(Passage(text="...", document_id="nda.txt", span=(160, 400)), GOLD)


def test_passage_without_position_is_matched_by_text_ignoring_case_and_spacing() -> None:
    text = (
        "7. RETURN.  the receiving party shall return all\nconfidential information "
        "within 30 days. 8. TERM."
    )
    assert holds_gold(Passage(text=text), GOLD)


def test_passage_that_cuts_the_gold_text_in_half_still_holds_it() -> None:
    text = "The Receiving Party shall return all Confidential Infor"
    assert holds_gold(Passage(text=text), GOLD)


def test_passage_sharing_only_a_few_words_does_not_hold_it() -> None:
    text = "The Receiving Party shall pay all taxes due under this Agreement within 30 days."
    assert not holds_gold(Passage(text=text), GOLD)


def test_empty_passage_never_holds_gold() -> None:
    assert not holds_gold(Passage(text="   "), GOLD)


def test_first_gold_rank_is_one_based_and_none_when_absent() -> None:
    passages = [
        Passage(text="a", document_id="nda.txt", span=(0, 50)),
        Passage(text="b", document_id="nda.txt", span=(150, 300)),
    ]
    assert first_gold_rank(passages, GOLD) == 2
    assert first_gold_rank(passages[:1], GOLD) is None


SPLIT = Gold(
    document_id="nda.txt",
    spans=((10, 60), (70, 76), (80, 160)),
    texts=(
        "6. The conditions of Paragraph 4 hereof shall not apply to information which:",
        "b. Was",
        "(iii) is developed by the receiving Party independent of such information",
    ),
)


def test_a_short_gold_fragment_alone_does_not_make_a_passage_hold_gold() -> None:
    # Six characters can occur anywhere; they must not count as the evidence.
    assert not holds_gold(Passage(text="The Seller b. Was paid in full."), SPLIT)


def test_a_long_gold_fragment_of_a_split_evidence_is_enough() -> None:
    text = (
        "Party (iii) is developed by the receiving Party independent of such information received"
    )
    assert holds_gold(Passage(text=text), SPLIT)


def test_gold_made_only_of_short_fragments_is_matched_as_a_whole() -> None:
    tiny = Gold(document_id="d", spans=((0, 3), (5, 8)), texts=("Yes", "No."))
    assert holds_gold(Passage(text="Answer: Yes or No. as stated"), tiny)
    assert not holds_gold(Passage(text="Yes, but nothing else"), tiny)
