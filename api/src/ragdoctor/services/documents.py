"""Adding documents to the library."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from ragbench import DatasetError
from ragbench.components.loaders.folder import read_document
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models

ALLOWED_SUFFIXES = (".txt", ".md", ".pdf")
MAX_BYTES = 20 * 1024 * 1024


def document_id_for(filename: str) -> str:
    """Return the id an uploaded file gets: ``uploads/<safe name>``."""
    name = Path(filename).name
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "document"
    return f"uploads/{safe}{suffix}"


def extract_text(filename: str, content: bytes) -> str:
    """Return the text of an uploaded ``.txt``, ``.md`` or ``.pdf`` file.

    Raises:
        ValueError: If the type is not allowed, the file is too large or holds no text.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"only {', '.join(ALLOWED_SUFFIXES)} files can be added")
    if len(content) > MAX_BYTES:
        raise ValueError("the file is larger than 20 MB")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"upload{suffix}"
        path.write_bytes(content)
        try:
            text = read_document(path)
        except DatasetError as error:
            raise ValueError(str(error)) from error
    if not text.strip():
        raise ValueError("no text could be read from the file (a scanned PDF needs OCR first)")
    return text


async def add_document(db: AsyncSession, filename: str, content: bytes) -> models.Document:
    """Store an uploaded file as a pending document; the caller enqueues indexing and commits.

    Raises:
        ValueError: If the file is unusable or a document with the same name exists.
    """
    text = extract_text(filename, content)
    document_id = document_id_for(filename)
    if await db.get(models.Document, document_id) is not None:
        raise ValueError(f"a document named {Path(document_id).name} already exists")
    document = models.Document(
        id=document_id,
        title=Path(filename).stem.replace("_", " ").replace("-", " "),
        source="uploads",
        text=text,
        origin="upload",
        status="pending",
    )
    db.add(document)
    await db.flush()
    return document
