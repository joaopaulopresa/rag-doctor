"""Whether a passage holds the gold evidence of a question."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

_SPACE = re.compile(r"\s+")
#: A passage holds the gold evidence by text when they share a run of at least this share of
#: the gold text (and at least `_MIN_SHARED` characters).
_SHARED_SHARE = 0.5
_MIN_SHARED = 30


@dataclass(frozen=True, slots=True)
class Passage:
    """A passage a system retrieved.

    Attributes:
        text: The passage text.
        document_id: The document it comes from, when the system says so in this
            application's ids.
        span: Its character range ``(start, end)`` in that document, when known.
    """

    text: str
    document_id: str | None = None
    span: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class Gold:
    """The gold evidence of a question.

    Attributes:
        document_id: The document that holds it.
        spans: Character ranges of the evidence in that document.
        texts: The text of each range.
    """

    document_id: str
    spans: tuple[tuple[int, int], ...]
    texts: tuple[str, ...]


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text).strip().lower()


def _shares_text(passage: str, gold: str) -> bool:
    if not passage or not gold:
        return False
    if gold in passage:
        return True
    match = SequenceMatcher(None, gold, passage, autojunk=False).find_longest_match()
    return match.size >= max(_MIN_SHARED, _SHARED_SHARE * len(gold))


def holds_gold(passage: Passage, gold: Gold) -> bool:
    """Return whether ``passage`` holds gold evidence.

    A passage with a known position is compared by position: same document and overlapping
    character ranges, which is how the engine's retrieval metrics decide relevance. A passage
    without a position (an external system returns only text) is compared by text: it must
    contain a gold text, or share a long run of it, ignoring case and white space.
    """
    if passage.document_id is not None and passage.span is not None:
        start, end = passage.span
        return passage.document_id == gold.document_id and any(
            min(end, gold_end) > max(start, gold_start) for gold_start, gold_end in gold.spans
        )
    text = _normalise(passage.text)
    return any(_shares_text(text, _normalise(gold_text)) for gold_text in gold.texts)


def first_gold_rank(passages: Sequence[Passage], gold: Gold) -> int | None:
    """Return the 1-based position of the first passage that holds gold, or ``None``."""
    for rank, passage in enumerate(passages, start=1):
        if holds_gold(passage, gold):
            return rank
    return None
