"""What the chat currently runs on: the active configuration and the indexed collection."""

from __future__ import annotations

from typing import Any

import ragbench as rb
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models

LIBRARY_KEY = "library"


def spec_of(configuration: models.Configuration) -> rb.PipelineConfig:
    """Return the engine configuration stored in ``configuration``."""
    return rb.PipelineConfig.model_validate(configuration.spec)


async def save_configuration(
    db: AsyncSession, spec: rb.PipelineConfig, *, name: str | None = None, origin: str = ""
) -> models.Configuration:
    """Store ``spec`` once (configurations are unique by their engine key) and return the row."""
    existing = await db.scalar(
        select(models.Configuration).where(models.Configuration.key == spec.key)
    )
    if existing is not None:
        return existing
    row = models.Configuration(
        key=spec.key,
        name=name or spec.display,
        spec=spec.model_dump(mode="json"),
        origin=origin,
    )
    db.add(row)
    await db.flush()
    return row


async def active_activation(db: AsyncSession) -> models.Activation | None:
    """Return the newest activation: the configuration the chat runs on."""
    return await db.scalar(select(models.Activation).order_by(models.Activation.id.desc()).limit(1))


async def get_state(db: AsyncSession, key: str) -> dict[str, Any]:
    """Return the stored value of ``key`` (empty if unset)."""
    row = await db.get(models.AppState, key)
    return dict(row.value) if row else {}


async def set_state(db: AsyncSession, key: str, value: dict[str, Any]) -> None:
    """Store ``value`` under ``key``."""
    statement = insert(models.AppState).values(key=key, value=value)
    await db.execute(statement.on_conflict_do_update(index_elements=["key"], set_={"value": value}))


async def live_collection(db: AsyncSession) -> str | None:
    """Return the collection the active configuration is indexed for, if any."""
    return (await get_state(db, LIBRARY_KEY)).get("collection")
