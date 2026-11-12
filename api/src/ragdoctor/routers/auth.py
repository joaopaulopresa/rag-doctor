"""Sign in and out."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ragdoctor import models
from ragdoctor.auth import COOKIE, Db, authenticate, current_user, issue_token, set_session_cookie
from ragdoctor.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


def user_view(user: models.User | None) -> dict[str, object] | None:
    return None if user is None else {"id": user.id, "email": user.email, "role": user.role}


@router.post("/login")
async def login(credentials: Credentials, response: Response, db: Db) -> dict[str, object]:
    user = await authenticate(db, credentials.email, credentials.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong e-mail or password.")
    set_session_cookie(response, issue_token(user))
    return {"user": user_view(user)}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(
    user: Annotated[models.User | None, Depends(current_user)],
) -> dict[str, object]:
    return {"user": user_view(user), "chat_requires_login": get_settings().chat_requires_login}
