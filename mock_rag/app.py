"""A deliberately weak RAG service, used as the external system the doctor audits in the demo.

It knows nothing of RAG Doctor. What makes it weak, on purpose:

* fixed windows of 120 words, cut without regard to sentences or sections;
* keyword overlap without any weighting, so common words count as much as rare ones;
* only the two best windows are given to the model;
* answers come from a small 8B model with a one-line instruction.

It returns the passage text but not where it comes from, as many hosted systems do.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

WINDOW = 120
PASSAGES = 2
WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "the a an and or of to in on for with by is are be this that does do any document "
    "consider under contract agreement what which how will can".split()
)

app = FastAPI(title="Acme support bot (weak RAG demo)")


@dataclass(frozen=True)
class Window:
    title: str
    text: str
    words: frozenset[str]


def terms(text: str) -> list[str]:
    """Lower-case words of ``text`` without stop words."""
    return [w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def windows(title: str, text: str, size: int = WINDOW) -> list[Window]:
    """Cut ``text`` into windows of ``size`` words."""
    words = text.split()
    return [
        Window(title, " ".join(words[i : i + size]), frozenset(terms(" ".join(words[i : i + size]))))
        for i in range(0, len(words), size)
    ]


def search(index: list[Window], question: str, k: int = PASSAGES) -> list[Window]:
    """Return the ``k`` windows sharing the most distinct words with the question."""
    wanted = set(terms(question))
    ranked = sorted(index, key=lambda w: len(wanted & w.words), reverse=True)
    return ranked[:k]


@lru_cache(maxsize=1)
def load_index() -> tuple[Window, ...]:
    """Read every text file below CORPUS_DIR once."""
    root = Path(os.environ.get("CORPUS_DIR", "/data"))
    found: list[Window] = []
    for path in sorted(root.rglob("corpus/**/*.txt")):
        title = path.stem.replace("_", " ")
        found.extend(windows(title, path.read_text(encoding="utf-8", errors="ignore")))
    return tuple(found)


def _cached_completion(body: dict[str, object]) -> str:
    cache = Path(os.environ.get("CACHE_DIR", ".cache"))
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    file = cache / f"{key}.json"
    if file.exists():
        return str(json.loads(file.read_text())["text"])
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"},
        json=body,
        timeout=60,
    )
    if response.status_code != 200:
        raise HTTPException(502, f"model provider answered {response.status_code}")
    text = str(response.json()["choices"][0]["message"]["content"] or "").strip()
    file.write_text(json.dumps({"text": text}))
    return text


class Ask(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "windows": len(load_index())}


@app.post("/ask")
def ask(body: Ask) -> dict[str, object]:
    index = load_index()
    if not index:
        load_index.cache_clear()
        raise HTTPException(503, "no documents loaded yet")
    found = search(list(index), body.query)
    sources = "\n\n".join(f"Source {n}: {w.text}" for n, w in enumerate(found, start=1))
    answer = _cached_completion(
        {
            "model": os.environ.get("SEED_MODEL", "meta-llama/llama-3.1-8b-instruct"),
            "temperature": 0,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": "Answer the customer's question using the sources."},
                {"role": "user", "content": f"{sources}\n\nQuestion: {body.query}"},
            ],
        }
    )
    return {"answer": answer, "sources": [{"title": w.title, "content": w.text} for w in found]}
