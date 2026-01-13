from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from app.core.db import get_session
from app.auth.jwt import mint_access, mint_refresh, decode_token
from app.auth.passwords import hash_pw, verify_pw
from app.auth.google import verify_google_id_token
from app.auth.apple import verify_apple_identity_token
from app.models.models import User, Account
from uuid import uuid4

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
