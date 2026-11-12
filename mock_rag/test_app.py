from app import search, terms, windows


def test_windows_cut_fixed_word_counts() -> None:
    parts = windows("doc", " ".join(f"w{i}" for i in range(250)), size=120)
    assert [len(p.text.split()) for p in parts] == [120, 120, 10]


def test_terms_drop_stop_words_and_short_words() -> None:
    assert terms("Does the NDA allow sharing of data?") == ["nda", "allow", "sharing", "data"]


def test_search_ranks_by_shared_words_without_weighting() -> None:
    index = windows("a", "insurance liability coverage", 3) + windows("b", "payment terms net thirty", 4)
    assert search(index, "what insurance coverage is required", k=1)[0].title == "a"
