"""Shared request dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ragdoctor.rag import Rag


def get_rag(request: Request) -> Rag:
    """Return the engine session opened at startup."""
    rag: Rag = request.app.state.rag
    return rag


RagDep = Annotated[Rag, Depends(get_rag)]
