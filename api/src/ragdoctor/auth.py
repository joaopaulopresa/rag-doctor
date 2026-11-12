"""Sign-in with two roles. The session is a signed token in an HTTP-only cookie."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdoctor import models
from ragdoctor.db import get_db
from ragdoctor.settings import get_settings

COOKIE = "rd_session"
ROLES = ("admin", "user")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password``."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    """Return whether ``password`` matches ``hashed``."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def issue_token(user: models.User) -> str:
    """Return a signed session token for ``user``."""
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(hours=settings.session_hours)
    claims = {"sub": str(user.id), "email": user.email, "role": user.role, "exp": expires}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session cookie to ``response``."""
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_hours * 3600,
        path="/",
    )


async def authenticate(db: AsyncSession, email: str, password: str) -> models.User | None:
    """Return the user with these credentials, or ``None``."""
    user = await db.scalar(select(models.User).where(models.User.email == email.lower().strip()))
    if user is None or not check_password(password, user.password_hash):
        return None
    return user


async def ensure_user(db: AsyncSession, email: str, password: str, role: str) -> None:
    """Create the user if it does not exist yet (used for the demo accounts)."""
    email = email.lower().strip()
    if await db.scalar(select(models.User).where(models.User.email == email)) is None:
        db.add(models.User(email=email, password_hash=hash_password(password), role=role))


async def current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> models.User | None:
    """Return the signed-in user, or ``None`` for an anonymous visitor."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return await db.get(models.User, int(claims["sub"]))


async def require_admin(
    user: Annotated[models.User | None, Depends(current_user)],
) -> models.User:
    """Allow only signed-in administrators."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to use the admin area.")
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The admin area needs the admin role.")
    return user


async def chat_access(
    user: Annotated[models.User | None, Depends(current_user)],
) -> models.User | None:
    """Allow the chat to everyone, unless the deployment requires a login for it."""
    if user is None and get_settings().chat_requires_login:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to use the chat.")
    return user


Admin = Annotated[models.User, Depends(require_admin)]
Db = Annotated[AsyncSession, Depends(get_db)]
