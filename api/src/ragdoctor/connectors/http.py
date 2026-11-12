"""Connector to an external RAG system over HTTP, described by a small mapping.

No access to the system's code is needed: the admin says where the question goes in the request
and where the answer and the cited passages are in the reply.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ragdoctor.doctor.evidence import Passage

PLACEHOLDER = "{{question}}"


class ConnectorError(Exception):
    """The external system failed or its reply does not fit the mapping."""


class ExternalSpec(BaseModel):
    """How to call an external RAG system and read its reply.

    Paths are dotted keys with list positions, for example ``data.sources`` or
    ``choices.0.message.content``.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    method: Literal["POST", "GET"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = Field(
        default_factory=lambda: {"question": PLACEHOLDER},
        description="JSON body (POST) or query parameters (GET); {{question}} is replaced.",
    )
    answer_path: str = "answer"
    passages_path: str | None = Field(
        default=None, description="List of passages in the reply; leave empty if there is none."
    )
    passage_text: str = Field(
        default="text", description="Text field of each passage; empty when passages are strings."
    )
    passage_document: str | None = None
    passage_start: str | None = None
    passage_end: str | None = None
    timeout_s: float = Field(default=60.0, gt=0, le=300)

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("the endpoint must be an http:// or https:// URL")
        return value

    def public(self) -> dict[str, Any]:
        """Return the mapping without header values, which may hold secrets."""
        data = self.model_dump()
        data["headers"] = dict.fromkeys(self.headers, "***")
        return data


def render(template: Any, question: str) -> Any:
    """Return ``template`` with every ``{{question}}`` replaced by ``question``."""
    if isinstance(template, str):
        return template.replace(PLACEHOLDER, question)
    if isinstance(template, list):
        return [render(item, question) for item in template]
    if isinstance(template, dict):
        return {key: render(value, question) for key, value in template.items()}
    return template


def get_path(data: Any, path: str) -> Any:
    """Return the value at a dotted ``path`` of ``data``, or ``None`` if it is missing."""
    node = data
    for part in [part for part in path.split(".") if part]:
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_reply(spec: ExternalSpec, data: Any) -> tuple[str, list[Passage] | None]:
    """Read the answer and the passages out of a reply.

    Raises:
        ConnectorError: If the answer is missing or the passages are not a list.
    """
    answer = get_path(data, spec.answer_path)
    if not isinstance(answer, str):
        raise ConnectorError(f"the reply has no text at {spec.answer_path!r}")
    if not spec.passages_path:
        return answer, None
    items = get_path(data, spec.passages_path)
    if items is None:
        items = []
    if not isinstance(items, list):
        raise ConnectorError(f"{spec.passages_path!r} in the reply is not a list")
    passages = []
    for item in items:
        text = item if not spec.passage_text else get_path(item, spec.passage_text)
        document = get_path(item, spec.passage_document) if spec.passage_document else None
        start = _int(get_path(item, spec.passage_start)) if spec.passage_start else None
        end = _int(get_path(item, spec.passage_end)) if spec.passage_end else None
        passages.append(
            Passage(
                text=str(text) if text is not None else "",
                document_id=str(document) if document is not None else None,
                span=(start, end) if start is not None and end is not None else None,
            )
        )
    return answer, passages


async def call(
    spec: ExternalSpec, question: str, client: httpx.AsyncClient
) -> tuple[str, list[Passage] | None, float, Any]:
    """Ask the external system ``question``.

    Returns:
        The answer, the passages (``None`` when the system returns none), the latency in
        seconds and the raw reply.

    Raises:
        ConnectorError: If the request fails or the reply does not fit the mapping.
    """
    payload = render(spec.body, question)
    started = time.perf_counter()
    try:
        if spec.method == "GET":
            response = await client.get(
                spec.url, params=payload, headers=spec.headers, timeout=spec.timeout_s
            )
        else:
            response = await client.post(
                spec.url, json=payload, headers=spec.headers, timeout=spec.timeout_s
            )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as error:
        raise ConnectorError(f"the system answered HTTP {error.response.status_code}") from error
    except (httpx.HTTPError, ValueError) as error:
        raise ConnectorError(f"the system could not be reached: {error}") from error
    latency = time.perf_counter() - started
    answer, passages = parse_reply(spec, data)
    return answer, passages, latency, data
