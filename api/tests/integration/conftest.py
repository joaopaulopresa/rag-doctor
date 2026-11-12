"""A throw-away database for API tests. Needs PostgreSQL: `docker compose up -d db`."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL", "postgresql://ragdoctor:ragdoctor@localhost:54330/ragdoctor"
)
TEST_DB = "ragdoctor_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


def _reachable() -> bool:
    try:
        psycopg.connect(ADMIN_URL, connect_timeout=2).close()
    except psycopg.Error:
        return False
    return True


pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def database_url() -> str:
    if not _reachable():
        pytest.skip("PostgreSQL is not reachable; run `docker compose up -d db`")
    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        connection.execute(f"CREATE DATABASE {TEST_DB}")
    os.environ.update(
        DATABASE_URL=TEST_URL,
        OPENROUTER_API_KEY="",
        JWT_SECRET="test-secret",
        ADMIN_EMAIL="admin@test.local",
        ADMIN_PASSWORD="admin-pass",
        USER_EMAIL="user@test.local",
        USER_PASSWORD="user-pass",
    )
    from ragdoctor.settings import get_settings

    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    config.set_main_option(
        "sqlalchemy.url", TEST_URL.replace("postgresql://", "postgresql+psycopg://")
    )
    command.upgrade(config, "head")
    return TEST_URL


@pytest.fixture(scope="session")
async def app(database_url: str) -> AsyncIterator[object]:
    from asgi_lifespan import LifespanManager

    from ragdoctor.auth import ensure_user
    from ragdoctor.db import dispose_engine, session_factory
    from ragdoctor.main import app as application

    await dispose_engine()
    async with session_factory()() as db:
        await ensure_user(db, "admin@test.local", "admin-pass", "admin")
        await ensure_user(db, "user@test.local", "user-pass", "user")
        await db.commit()
    async with LifespanManager(application):
        yield application
    await dispose_engine()


@pytest.fixture
async def client(app: object) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:  # type: ignore[arg-type]
        yield http


@pytest.fixture
async def admin(client: AsyncClient) -> AsyncClient:
    response = await client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "admin-pass"}
    )
    assert response.status_code == 200
    return client
