"""Mapping a question into an external system's request and its reply back."""

import pytest

from ragdoctor.connectors.http import ConnectorError, ExternalSpec, get_path, parse_reply, render


def spec(**overrides: object) -> ExternalSpec:
    base = {
        "url": "http://rag.example/ask",
        "body": {"query": "{{question}}", "options": {"k": 3}},
        "answer_path": "data.answer",
        "passages_path": "data.sources",
        "passage_text": "content",
    }
    return ExternalSpec.model_validate({**base, **overrides})


def test_template_puts_the_question_into_every_placeholder_and_keeps_other_values() -> None:
    body = render({"q": "{{question}}", "meta": ["Q: {{question}}", 3, None]}, 'Is "X" ok?')
    assert body == {"q": 'Is "X" ok?', "meta": ['Q: Is "X" ok?', 3, None]}


def test_path_reads_nested_keys_and_list_positions() -> None:
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    assert get_path(data, "a.b.1.c") == 2
    assert get_path(data, "a.missing") is None
    assert get_path(data, "a.b.9.c") is None
    assert get_path(data, "") == data


def test_reply_with_text_only_passages_maps_to_passages_without_position() -> None:
    reply = {
        "data": {"answer": "Thirty days [1].", "sources": [{"content": "a"}, {"content": "b"}]}
    }
    answer, passages = parse_reply(spec(), reply)
    assert answer == "Thirty days [1]."
    assert passages is not None
    assert [p.text for p in passages] == ["a", "b"]
    assert passages[0].span is None


def test_passages_given_as_plain_strings_are_accepted() -> None:
    reply = {"data": {"answer": "x", "sources": ["first", "second"]}}
    _, passages = parse_reply(spec(passage_text=""), reply)
    assert passages is not None
    assert [p.text for p in passages] == ["first", "second"]


def test_passages_with_document_and_offsets_keep_their_position() -> None:
    reply = {
        "data": {
            "answer": "x",
            "sources": [{"content": "t", "doc": "nda.txt", "start": 5, "end": 9}],
        }
    }
    custom = spec(passage_document="doc", passage_start="start", passage_end="end")
    _, passages = parse_reply(custom, reply)
    assert passages is not None
    assert passages[0].document_id == "nda.txt"
    assert passages[0].span == (5, 9)


def test_system_without_passages_gives_none() -> None:
    answer, passages = parse_reply(spec(passages_path=None), {"data": {"answer": "x"}})
    assert answer == "x"
    assert passages is None


def test_missing_answer_is_an_error_that_names_the_path() -> None:
    with pytest.raises(ConnectorError, match=r"data\.answer"):
        parse_reply(spec(), {"data": {}})


def test_passages_path_that_is_not_a_list_is_an_error() -> None:
    with pytest.raises(ConnectorError, match="list"):
        parse_reply(spec(), {"data": {"answer": "x", "sources": "oops"}})


def test_only_http_urls_are_accepted() -> None:
    with pytest.raises(ValueError, match="http"):
        spec(url="file:///etc/passwd")
