"""Account identity and revocable browser sessions for the public API."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import Db
from app.models import Account, AuthSession, Participant
from app.schemas import LoginRequest, ParticipantRead, RegisterRequest

router = APIRouter(tags=["auth"])
COOKIE_NAME = "ghosttech_session"
SESSION_AGE = timedelta(days=7)
PBKDF2_ROUNDS = 310_000


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ROUNDS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256" or int(rounds) != PBKDF2_ROUNDS:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def optional_participant(request: Request, db: Db) -> Participant | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = db.get(AuthSession, _token_hash(token))
    if not session:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    return session.account.participant


def require_participant(
    participant: Annotated[Participant | None, Depends(optional_participant)],
) -> Participant:
    if participant is None:
        raise HTTPException(401, "Войдите в аккаунт")
    return participant


def require_business(
    participant: Annotated[Participant, Depends(require_participant)],
) -> Participant:
    if participant.role != "business":
        raise HTTPException(403, "Доступно только бизнес-профилю")
    return participant


def require_student(
    participant: Annotated[Participant, Depends(require_participant)],
) -> Participant:
    if participant.role != "student":
        raise HTTPException(403, "Доступно только студенту")
    return participant


def _create_session(request: Request, response: Response, db: Db, account: Account) -> None:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_token_hash(token),
            account_id=account.id,
            expires_at=datetime.now(timezone.utc) + SESSION_AGE,
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_AGE.total_seconds()),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=ParticipantRead, status_code=201)
def register(data: RegisterRequest, request: Request, response: Response, db: Db):
    participant = Participant(name=data.name, role=data.role, is_demo=False)
    account = Account(
        participant=participant, email=data.email, password_hash=_password_hash(data.password)
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Аккаунт с таким адресом уже существует") from None
    _create_session(request, response, db, account)
    return participant


@router.post("/auth/login", response_model=ParticipantRead)
def login(data: LoginRequest, request: Request, response: Response, db: Db):
    account = db.scalar(select(Account).where(Account.email == data.email))
    if account is None or not _password_matches(data.password, account.password_hash):
        raise HTTPException(401, "Неверный адрес или пароль")
    _create_session(request, response, db, account)
    return account.participant


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: Db):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = db.get(AuthSession, _token_hash(token))
        if session:
            db.delete(session)
            db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/auth/me", response_model=ParticipantRead)
def me(participant: Annotated[Participant, Depends(require_participant)]):
    return participant
