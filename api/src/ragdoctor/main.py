"""The FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ragbench as rb
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ragdoctor import __version__
from ragdoctor.db import dispose_engine, init_engine
from ragdoctor.rag import open_rag
from ragdoctor.routers import auth, chat, doctor, lab, library
from ragdoctor.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

#: Engine errors and the HTTP status each one means to a client.
ERROR_STATUS = {
    rb.ConfigError: 422,
    rb.DatasetError: 422,
    rb.ExperimentError: 409,
    rb.ProviderError: 502,
    rb.StoreError: 503,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine()
    async with open_rag(get_settings()) as rag:
        app.state.rag = rag
        yield
    await dispose_engine()


app = FastAPI(title="RAG Doctor", version=__version__, lifespan=lifespan)


@app.exception_handler(rb.RagBenchError)
async def engine_error(request: Request, error: rb.RagBenchError) -> JSONResponse:
    code = next((c for kind, c in ERROR_STATUS.items() if isinstance(error, kind)), 500)
    return JSONResponse({"detail": str(error)}, status_code=code)


for module in (auth, chat, library, lab, doctor):
    app.include_router(module.router)
