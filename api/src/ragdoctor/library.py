"""The library: the documents and gold questions held by this application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import ragbench as rb
from ragbench.core.hashing import stable_hash
from ragbench.experiment.runner import collection_name
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models

CORPUS_NAME = "library"


@dataclass(frozen=True, slots=True)
class Library:
    """A consistent view of the documents and the accepted questions.

    Attributes:
        documents: Every document, ordered by id.
        questions: Accepted questions whose evidence lies in ``documents``, ordered by id.
    """

    documents: tuple[rb.Document, ...]
    questions: tuple[rb.Question, ...]

    @property
    def corpus(self) -> rb.Corpus:
        """The library as the engine's corpus type."""
        return rb.Corpus(name=CORPUS_NAME, documents=self.documents, questions=self.questions)

    @property
    def collection(self) -> str:
        """Name of the document collection; it changes whenever the documents change."""
        return collection_name(self.corpus)

    def question(self, question_id: str) -> rb.Question | None:
        """Return the accepted question with this id, if any."""
        return next((q for q in self.questions if q.id == question_id), None)


def to_engine_document(row: models.Document) -> rb.Document:
    """Convert a stored document to the engine's type."""
    return rb.Document(id=row.id, text=row.text, title=row.title, source=row.source)


def to_engine_question(row: models.Question) -> rb.Question:
    """Convert a stored question to the engine's type.

    Raises:
        ValueError: If the question has no document or no evidence span.
    """
    if row.document_id is None or not row.spans:
        raise ValueError(f"question {row.id} has no gold evidence")
    spans = tuple(sorted(rb.Span(int(start), int(end)) for start, end in row.spans))
    return rb.Question(
        id=row.id, text=row.text, document_id=row.document_id, spans=spans, source=row.source
    )


async def load_library(db: AsyncSession, *, include_pending: bool = False) -> Library:
    """Read the library from the database.

    Args:
        db: Database session.
        include_pending: Also include documents that are not indexed yet (used while indexing).
    """
    statuses = ("ready", "pending") if include_pending else ("ready",)
    documents = (
        await db.scalars(
            select(models.Document)
            .where(models.Document.status.in_(statuses))
            .order_by(models.Document.id)
        )
    ).all()
    known = {document.id for document in documents}
    questions = (
        await db.scalars(
            select(models.Question)
            .where(models.Question.status == "accepted")
            .order_by(models.Question.id)
        )
    ).all()
    return Library(
        documents=tuple(to_engine_document(document) for document in documents),
        questions=tuple(
            to_engine_question(question)
            for question in questions
            if question.document_id in known and question.spans
        ),
    )


def write_snapshot(library: Library, directory: Path) -> Path:
    """Write the library to a file the ``library_snapshot`` loader reads; return its path.

    The file name is a hash of the content, so the same library always gives the same path and
    an experiment on it keeps its run id.
    """
    data = {
        "documents": [
            {"id": d.id, "text": d.text, "title": d.title, "source": d.source}
            for d in library.documents
        ],
        "questions": [
            {
                "id": q.id,
                "text": q.text,
                "document_id": q.document_id,
                "spans": [[span.start, span.end] for span in q.spans],
                "source": q.source,
            }
            for q in library.questions
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"library-{stable_hash(data, length=16)}.json"
    if not path.exists():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@rb.register_loader("library_snapshot")
class SnapshotLoader:
    """Loads a library snapshot written by `write_snapshot`.

    The engine's experiment runner loads its corpus through a registered loader; this one lets
    it run on the documents and reviewed questions of the application.

    Args:
        resources: Unused; present so the class fits the factory signature.
        path: The snapshot file.
    """

    def __init__(self, resources: object, path: str) -> None:
        del resources
        self._path = Path(path)

    def load(self) -> rb.Corpus:
        """Read the snapshot.

        Raises:
            DatasetError: If the file is missing or malformed.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return rb.Corpus(
                name=CORPUS_NAME,
                documents=tuple(rb.Document(**item) for item in data["documents"]),
                questions=tuple(
                    rb.Question(
                        id=item["id"],
                        text=item["text"],
                        document_id=item["document_id"],
                        spans=tuple(rb.Span(start, end) for start, end in item["spans"]),
                        source=item["source"],
                    )
                    for item in data["questions"]
                ),
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise rb.DatasetError(f"cannot read library snapshot {self._path}: {error}") from error
