"""API behaviour against a real database. No model is called."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from ragdoctor import models
from ragdoctor.db import session_factory
from ragdoctor.doctor.diagnosis import Outcome
from ragdoctor.jobs.queue import claim, enqueue

pytestmark = pytest.mark.integration

DOC_TEXT = (
    "1. Term. This agreement lasts two years. "
    "2. Notice. Either party may end it with sixty days of notice."
)


@pytest.fixture
async def library(app: object) -> None:
    async with session_factory()() as db:
        for table in (models.ExaminationCase, models.Examination, models.Question, models.Document):
            await db.execute(delete(table))
        db.add(
            models.Document(
                id="contracts/a.txt", title="a", source="contracts", text=DOC_TEXT, status="ready"
            )
        )
        await db.flush()
        start = DOC_TEXT.index("Either party")
        db.add(
            models.Question(
                id="q-1",
                text="How can the agreement be ended?",
                document_id="contracts/a.txt",
                spans=[[start, len(DOC_TEXT)]],
                source="contracts",
                status="accepted",
            )
        )
        await db.commit()


async def test_sign_in_with_a_wrong_password_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "x"}
    )
    assert response.status_code == 401


async def test_the_admin_area_needs_a_session_and_the_admin_role(client: AsyncClient) -> None:
    assert (await client.get("/api/admin/catalog")).status_code == 401
    await client.post("/api/auth/login", json={"email": "user@test.local", "password": "user-pass"})
    assert (await client.get("/api/admin/catalog")).status_code == 403
    assert (await client.get("/api/auth/me")).json()["user"]["role"] == "user"


async def test_an_admin_sees_the_catalogue(admin: AsyncClient) -> None:
    catalog = (await admin.get("/api/admin/catalog")).json()
    assert catalog["initial"]["reranker"] == "cohere-rerank-5-fast"
    assert any(option["expensive"] for option in catalog["rerankers"])


async def test_question_import_keeps_only_evidence_that_matches_the_document(
    admin: AsyncClient, library: None
) -> None:
    good = {
        "query": "How long does it last?",
        "reviewed": True,
        "snippets": [{"file_path": "contracts/a.txt", "span": [10, 39], "answer": DOC_TEXT[10:39]}],
    }
    bad = {
        "query": "Wrong span",
        "reviewed": True,
        "snippets": [{"file_path": "contracts/a.txt", "span": [0, 5], "answer": "nope!"}],
    }
    unknown = {
        "query": "Unknown file",
        "snippets": [{"file_path": "x.txt", "span": [0, 1], "answer": "x"}],
    }
    files = {"file": ("questions.json", __import__("json").dumps({"tests": [good, bad, unknown]}))}
    result = (await admin.post("/api/admin/questions/import", files=files)).json()
    assert result == {"added": 1, "updated": 0, "skipped": 2}
    exported = (await admin.get("/api/admin/questions/export")).json()["tests"]
    assert {t["query"] for t in exported} == {
        "How can the agreement be ended?",
        "How long does it last?",
    }


async def test_a_question_without_evidence_cannot_be_accepted(
    admin: AsyncClient, library: None
) -> None:
    async with session_factory()() as db:
        db.add(
            models.Question(
                id="feedback-0000", text="Who pays?", spans=[], status="draft", origin="feedback"
            )
        )
        await db.commit()
    refused = await admin.patch("/api/admin/questions/feedback-0000", json={"status": "accepted"})
    assert refused.status_code == 422
    fixed = await admin.patch(
        "/api/admin/questions/feedback-0000",
        json={
            "document_id": "contracts/a.txt",
            "evidence": "This agreement lasts two years.",
            "status": "accepted",
        },
    )
    assert fixed.status_code == 200
    assert fixed.json()["question"]["evidence"] == ["This agreement lasts two years."]


async def test_two_workers_never_claim_the_same_job(app: object) -> None:
    factory = session_factory()
    async with factory() as db:
        await db.execute(delete(models.Job))
        for number in range(2):
            await enqueue(db, "index", {}, title=f"job {number}")
        await db.commit()

    async def take() -> int | None:
        async with factory() as db:
            job = await claim(db)
            await asyncio.sleep(0.2)
            return job.id if job else None

    first, second = await asyncio.gather(take(), take())
    assert first is not None and second is not None and first != second


async def _examination(outcomes: dict[str, str]) -> int:
    async with session_factory()() as db:
        exam = models.Examination(
            label="t", target_kind="external", target={}, question_ids=list(outcomes)
        )
        db.add(exam)
        await db.flush()
        for question_id, outcome in outcomes.items():
            db.add(
                models.ExaminationCase(
                    examination_id=exam.id,
                    question_id=question_id,
                    outcome=outcome,
                    data={
                        "question": question_id,
                        "scores": {
                            "correctness": 2 if outcome == "correct" else 0,
                            "faithfulness": 2,
                            "citation": 2,
                        },
                    },
                )
            )
        await db.commit()
        return exam.id


async def test_marking_wrong_gold_recomputes_the_summary_and_rejects_the_question(
    admin: AsyncClient, library: None
) -> None:
    exam = await _examination({"q-1": Outcome.NOT_RETRIEVED.value})
    case_id = (await admin.get(f"/api/admin/examinations/{exam}/cases")).json()["cases"][0]["id"]
    marked = (
        await admin.post(f"/api/admin/cases/{case_id}/wrong-gold", json={"wrong": True})
    ).json()
    assert marked["summary"]["counts"]["wrong_gold"] == 1
    assert marked["summary"]["evaluated"] == 0
    questions = (await admin.get("/api/admin/questions?status_filter=rejected")).json()["questions"]
    assert [q["id"] for q in questions] == ["q-1"]
    restored = (
        await admin.post(f"/api/admin/cases/{case_id}/wrong-gold", json={"wrong": False})
    ).json()
    assert restored["case"]["outcome"] == Outcome.NOT_RETRIEVED.value


async def test_before_and_after_compares_the_same_questions(admin: AsyncClient) -> None:
    before = await _examination(
        {f"x{i}": ("correct" if i < 2 else "not_retrieved") for i in range(10)}
    )
    after = await _examination(
        {f"x{i}": ("correct" if i < 8 else "not_retrieved") for i in range(10)}
    )
    result = (await admin.get(f"/api/admin/compare?before={before}&after={after}")).json()
    assert result["counts"] == {"fixed": 6, "broken": 0, "still_wrong": 2, "still_correct": 2}
    assert result["difference"]["mean"] == pytest.approx(0.6)
    page = await admin.get(f"/api/admin/compare/report?before={before}&after={after}")
    assert page.status_code == 200
    assert "Before and after" in page.text and "<script" not in page.text
