from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.db import get_session
from app.auth.jwt import mint_access, mint_refresh, decode_token
from app.auth.passwords import hash_pw, verify_pw
from app.auth.google import verify_google_id_token
from app.auth.apple import verify_apple_identity_token
from app.models.models import User, Account, PasswordResetToken
from app.core.config import settings
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access: str
    refresh: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetRequestOut(BaseModel):
    ok: bool = True
    reset_token: str | None = None
    expires_at: str | None = None


class PasswordResetConfirmIn(BaseModel):
    token: str
    new_password: str


def _hash_reset_token(token: str) -> str:
    raw = f"{token}{settings.SECRET_KEY}".encode()
    return hashlib.sha256(raw).hexdigest()


@router.post("/signup", response_model=TokenOut)
async def signup(body: SignupIn, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="email_exists")
    user = User(id=uuid4(), email=body.email, name=body.name, password_hash=hash_pw(body.password))
    session.add(user)
    await session.commit()
    return TokenOut(access=mint_access(str(user.id)), refresh=mint_refresh(str(user.id)))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()
    if not user or not user.password_hash or not verify_pw(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return TokenOut(access=mint_access(str(user.id)), refresh=mint_refresh(str(user.id)))


class GoogleIn(BaseModel):
    id_token: str


@router.post("/google", response_model=TokenOut)
async def google_exchange(body: GoogleIn, session: AsyncSession = Depends(get_session)):
    import os
    if os.getenv("ENABLE_GOOGLE_AUTH", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="google_auth_disabled")
    try:
        info = verify_google_id_token(body.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_google_token")
    subject = info["sub"]
    email = info.get("email")
    name = info.get("name")
    pic = info.get("picture")
    user = await _upsert_oauth_user(session, "google", subject, email, name, pic, info)
    return TokenOut(access=mint_access(str(user.id)), refresh=mint_refresh(str(user.id)))


class AppleIn(BaseModel):
    identity_token: str


@router.post("/apple", response_model=TokenOut)
async def apple_exchange(body: AppleIn, session: AsyncSession = Depends(get_session)):
    claims = await verify_apple_identity_token(body.identity_token)
    subject = claims["sub"]
    email = claims.get("email")
    name = claims.get("name")
    user = await _upsert_oauth_user(session, "apple", subject, email, name, None, claims)
    return TokenOut(access=mint_access(str(user.id)), refresh=mint_refresh(str(user.id)))


class RefreshIn(BaseModel):
    refresh: str


@router.post("/refresh", response_model=TokenOut)
async def refresh_token(body: RefreshIn):
    data = decode_token(body.refresh)
    if data.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="invalid_refresh")
    uid = data["sub"]
    return TokenOut(access=mint_access(uid), refresh=mint_refresh(uid))


@router.post("/password-reset/request", response_model=PasswordResetRequestOut)
async def request_password_reset(body: PasswordResetRequestIn, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()
    if not user or not user.password_hash:
        return PasswordResetRequestOut(ok=True)

    now = datetime.now(timezone.utc)
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )

    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=1)
    session.add(
        PasswordResetToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=_hash_reset_token(token),
            expires_at=expires_at,
        )
    )
    await session.commit()

    if settings.APP_ENV != "prod":
        return PasswordResetRequestOut(ok=True, reset_token=token, expires_at=expires_at.isoformat())
    return PasswordResetRequestOut(ok=True)


@router.post("/password-reset/confirm", response_model=TokenOut)
async def confirm_password_reset(body: PasswordResetConfirmIn, session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    token_hash = _hash_reset_token(body.token)
    res = await session.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    prt = res.scalar_one_or_none()
    if not prt or prt.used_at or prt.expires_at < now:
        raise HTTPException(status_code=400, detail="invalid_reset_token")
    user = await session.get(User, prt.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="invalid_reset_token")
    user.password_hash = hash_pw(body.new_password)
    prt.used_at = now
    await session.commit()
    return TokenOut(access=mint_access(str(user.id)), refresh=mint_refresh(str(user.id)))


async def _upsert_oauth_user(
    session: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str | None,
    name: str | None,
    avatar_url: str | None,
    raw_profile: dict,
) -> User:
    res = await session.execute(
        select(User).join(Account, Account.user_id == User.id).where(
            Account.provider == provider, Account.provider_user_id == provider_user_id
        )
    )
    user = res.scalar_one_or_none()
    if user:
        return user
    # Otherwise create user + account
    user = User(id=uuid4(), email=email, name=name, avatar_url=avatar_url)
    session.add(user)
    await session.flush()
    acct = Account(user_id=user.id, provider=provider, provider_user_id=provider_user_id, raw_profile=raw_profile)
    session.add(acct)
    await session.commit()
    return user
