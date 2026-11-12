"""Command line: ``ragdoctor bootstrap`` and ``ragdoctor worker``."""

from __future__ import annotations

import asyncio
import logging
import sys

from ragdoctor.db import dispose_engine, session_factory
from ragdoctor.demo import bootstrap


async def _bootstrap() -> None:
    try:
        async with session_factory()() as db:
            await bootstrap(db)
    finally:
        await dispose_engine()


def main() -> None:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "bootstrap":
        asyncio.run(_bootstrap())
    elif command == "worker":
        from ragdoctor.jobs.worker import main as worker

        asyncio.run(worker())
    else:
        print("usage: ragdoctor bootstrap | worker", file=sys.stderr)
        raise SystemExit(2)
