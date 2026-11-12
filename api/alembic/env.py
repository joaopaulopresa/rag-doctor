"""Alembic environment: migrations for the application's own tables (schema ``public``)."""

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ragdoctor.models import Base
from ragdoctor.settings import get_settings

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or get_settings().sqlalchemy_url
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
        await connection.commit()
    await engine.dispose()


asyncio.run(_online())
