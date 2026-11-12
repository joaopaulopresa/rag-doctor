"""The application's own tables. The engine keeps its tables in a separate schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base."""

    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}  # noqa: RUF012


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """A person who can sign in. ``role`` is ``admin`` or ``user``."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now()


class Document(Base):
    """A source document of the library. ``id`` is what the engine calls the document id."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    source: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), default="upload")  # dataset | upload
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|ready|failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


class Question(Base):
    """A question with its gold evidence. Only ``accepted`` questions count as gold."""

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    spans: Mapped[list[Any]] = mapped_column(default=list)  # [[start, end], ...]
    source: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|accepted|rejected
    origin: Mapped[str] = mapped_column(String(16), default="generated")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_questions_status", "status"),)


class Configuration(Base):
    """A saved pipeline configuration (one ``PipelineConfig`` of the engine)."""

    __tablename__ = "configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    spec: Mapped[dict[str, Any]] = mapped_column()
    origin: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = _now()


class Activation(Base):
    """One entry of the history of what the chat ran on. The newest row is the active one."""

    __tablename__ = "activations"

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("configurations.id"))
    note: Mapped[str] = mapped_column(String(255), default="")
    activated_by: Mapped[str] = mapped_column(String(255), default="")
    activated_at: Mapped[datetime] = _now()

    configuration: Mapped[Configuration] = relationship(lazy="joined")


class ChatMessage(Base):
    """One question asked in the chat, with what was answered and from which passages."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    passages: Mapped[list[Any]] = mapped_column(default=list)
    citations: Mapped[list[Any]] = mapped_column(default=list)
    config_key: Mapped[str] = mapped_column(String(32), default="")
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _now()


class Job(Base):
    """A unit of background work, claimed by the worker with ``FOR UPDATE SKIP LOCKED``."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    title: Mapped[str] = mapped_column(String(255), default="")
    done: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_jobs_status_id", "status", "id"),)


class Experiment(Base):
    """An experiment started from the lab; results live in the engine's run tables."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict[str, Any]] = mapped_column()
    run_id: Mapped[str] = mapped_column(String(128), default="")
    baseline_key: Mapped[str] = mapped_column(String(32), default="")
    examination_id: Mapped[int | None] = mapped_column(
        ForeignKey("examinations.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _now()

    job: Mapped[Job | None] = relationship(lazy="joined")


class ExternalSystem(Base):
    """An outside RAG system reached over HTTP, with the mapping of its request and reply."""

    __tablename__ = "external_systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    spec: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = _now()


class Examination(Base):
    """One run of the doctor over a question set, on this app or on an external system."""

    __tablename__ = "examinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255))
    target_kind: Mapped[str] = mapped_column(String(16))  # own | external
    configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("configurations.id"), nullable=True
    )
    external_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("external_systems.id", ondelete="SET NULL"), nullable=True
    )
    target: Mapped[dict[str, Any]] = mapped_column(default=dict)  # snapshot of what was examined
    question_ids: Mapped[list[Any]] = mapped_column(default=list)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _now()

    job: Mapped[Job | None] = relationship(lazy="joined")
    configuration: Mapped[Configuration | None] = relationship(lazy="joined")
    external_system: Mapped[ExternalSystem | None] = relationship(lazy="joined")


class ExaminationCase(Base):
    """The doctor's finding for one question of an examination."""

    __tablename__ = "examination_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("examinations.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32))
    wrong_gold: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)

    __table_args__ = (UniqueConstraint("examination_id", "question_id"),)


class AppState(Base):
    """Small key-value facts, for example whether the demo data was loaded."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
