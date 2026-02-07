import secrets
import string
from uuid import UUID, uuid4

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user_id
from app.core.config import settings
from app.core.db import get_session
from app.models.models import Outfit, OutfitItem, ItemImage, VoteSession, VoteSessionOutfit, Vote
from app.storage.r2 import presign_get, R2_CDN_BASE
from app.schemas.votes import (
    VoteSessionCreateIn,
    VoteSessionCreateOut,
    VoteSessionOut,
    VoteSessionOutfitOut,
    VoteOutfitItemOut,
    VoteIn,
    VoteOut,
)

router = APIRouter(prefix="/votes", tags=["votes"])


def _share_url(request: Request, code: str) -> str:
    if settings.VOTE_SHARE_BASE_URL:
        return f"{settings.VOTE_SHARE_BASE_URL.rstrip('/')}/{code}"
    base = str(request.base_url).rstrip("/")
    return f"{base}{settings.API_PREFIX}/votes/sessions/{code}"

def _public_image_url(key: str, bucket: str | None) -> str:
    if R2_CDN_BASE:
        return f"{R2_CDN_BASE}/{key}"
    return presign_get(key, bucket=bucket)


def _generate_share_code(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _parse_outfit_ids(outfit_ids: list[str]) -> list[UUID]:
    parsed: list[UUID] = []
    for raw in outfit_ids:
        try:
            parsed.append(UUID(str(raw)))
        except Exception as e:
            raise HTTPException(status_code=400, detail="invalid_outfit_id") from e
    return parsed


@router.post("/sessions", response_model=VoteSessionCreateOut)
async def create_vote_session(
    payload: VoteSessionCreateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    if not payload.outfit_ids:
        raise HTTPException(status_code=422, detail="outfit_ids_required")
    if len(payload.outfit_ids) < 2:
        raise HTTPException(status_code=422, detail="at_least_two_outfits_required")
    if len(set(payload.outfit_ids)) != len(payload.outfit_ids):
        raise HTTPException(status_code=422, detail="duplicate_outfit_ids")

    outfit_ids = _parse_outfit_ids(payload.outfit_ids)

    res = await session.execute(
        select(Outfit.id).where(Outfit.id.in_(outfit_ids), Outfit.user_id == user_id)
    )
    found = {str(row[0]) for row in res.all()}
    if len(found) != len(outfit_ids):
        raise HTTPException(status_code=404, detail="outfit_not_found")

    vote_session = None
    share_code = None
    ttl_hours = max(settings.VOTE_SESSION_TTL_HOURS, 0)
    expires_at = None
    if ttl_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    for _ in range(6):
        share_code = _generate_share_code()
        vote_session = VoteSession(id=uuid4(), user_id=user_id, share_code=share_code, expires_at=expires_at)
        session.add(vote_session)
        try:
            await session.flush()
            break
        except IntegrityError:
            await session.rollback()
            vote_session = None
            share_code = None
    if not vote_session or not share_code:
        raise HTTPException(status_code=500, detail="share_code_unavailable")

    for idx, outfit_id in enumerate(outfit_ids):
        session.add(
            VoteSessionOutfit(
                id=uuid4(),
                session_id=vote_session.id,
                outfit_id=outfit_id,
                position=idx,
            )
        )

    await session.commit()
    await session.refresh(vote_session)

    return VoteSessionCreateOut(
        session_id=str(vote_session.id),
        share_code=share_code,
        share_url=_share_url(request, share_code),
        created_at=vote_session.created_at.isoformat() if vote_session.created_at else None,
    )


@router.get("/sessions/{code}", response_model=VoteSessionOut)
async def get_vote_session(
    code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(select(VoteSession).where(VoteSession.share_code == code))
    vote_session = res.scalar_one_or_none()
    if not vote_session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if vote_session.expires_at and vote_session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="session_expired")

    outfits_res = await session.execute(
        select(
            VoteSessionOutfit.outfit_id,
            VoteSessionOutfit.position,
            Outfit.name,
            Outfit.primary_image_url,
        )
        .join(Outfit, Outfit.id == VoteSessionOutfit.outfit_id)
        .where(VoteSessionOutfit.session_id == vote_session.id)
        .order_by(VoteSessionOutfit.position.asc())
    )
    outfits_rows = outfits_res.all()

    counts_res = await session.execute(
        select(Vote.outfit_id, func.count(Vote.id))
        .where(Vote.session_id == vote_session.id)
        .group_by(Vote.outfit_id)
    )
    count_map = {str(outfit_id): int(count) for outfit_id, count in counts_res.all()}
    total_votes = sum(count_map.values())

    outfit_ids = [row[0] for row in outfits_rows]
    items_res = await session.execute(
        select(
            OutfitItem.outfit_id,
            OutfitItem.item_id,
            OutfitItem.slot,
            OutfitItem.position,
        ).where(OutfitItem.outfit_id.in_(outfit_ids))
    )
    outfit_items_rows = items_res.all()

    item_ids = list({row[1] for row in outfit_items_rows})
    item_images: dict[str, str | None] = {}
    if item_ids:
        images_res = await session.execute(
            select(ItemImage.item_id, ItemImage.url, ItemImage.key, ItemImage.bucket)
            .where(ItemImage.item_id.in_(item_ids))
            .order_by(ItemImage.created_at.asc())
        )
        for item_id, url, key, bucket in images_res.all():
            key_id = str(item_id)
            if key_id in item_images:
                continue
            if url:
                item_images[key_id] = url
            elif key:
                item_images[key_id] = _public_image_url(key, bucket)
            else:
                item_images[key_id] = None

    items_by_outfit: dict[str, list[VoteOutfitItemOut]] = {}
    for outfit_id, item_id, slot, position in outfit_items_rows:
        outfit_key = str(outfit_id)
        items_by_outfit.setdefault(outfit_key, []).append(
            VoteOutfitItemOut(
                item_id=str(item_id),
                slot=slot,
                position=position or 0,
                image_url=item_images.get(str(item_id)),
            )
        )
    for items in items_by_outfit.values():
        items.sort(key=lambda x: x.position)

    outfits = [
        VoteSessionOutfitOut(
            outfit_id=str(outfit_id),
            name=name,
            primary_image_url=primary_image_url,
            vote_count=count_map.get(str(outfit_id), 0),
            position=position,
            items=items_by_outfit.get(str(outfit_id), []),
        )
        for outfit_id, position, name, primary_image_url in outfits_rows
    ]

    return VoteSessionOut(
        session_id=str(vote_session.id),
        share_code=vote_session.share_code,
        share_url=_share_url(request, vote_session.share_code),
        created_at=vote_session.created_at.isoformat() if vote_session.created_at else None,
        outfits=outfits,
        total_votes=total_votes,
    )


@router.post("/sessions/{code}/vote", response_model=VoteOut)
async def vote_for_outfit(
    code: str,
    payload: VoteIn,
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(select(VoteSession).where(VoteSession.share_code == code))
    vote_session = res.scalar_one_or_none()
    if not vote_session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if vote_session.expires_at and vote_session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="session_expired")

    try:
        outfit_id = UUID(str(payload.outfit_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid_outfit_id") from e

    res = await session.execute(
        select(VoteSessionOutfit.id).where(
            VoteSessionOutfit.session_id == vote_session.id,
            VoteSessionOutfit.outfit_id == outfit_id,
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="outfit_not_in_session")

    if not payload.voter_hash:
        raise HTTPException(status_code=400, detail="voter_hash_required")

    res = await session.execute(
        select(Vote).where(
            Vote.session_id == vote_session.id,
            Vote.voter_hash == payload.voter_hash,
        )
    )
    existing_vote = res.scalar_one_or_none()
    if existing_vote:
        existing_vote.outfit_id = outfit_id
    else:
        session.add(
            Vote(
                id=uuid4(),
                session_id=vote_session.id,
                outfit_id=outfit_id,
                voter_hash=payload.voter_hash,
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="vote_update_failed")

    count_res = await session.execute(
        select(func.count(Vote.id)).where(
            Vote.session_id == vote_session.id,
            Vote.outfit_id == outfit_id,
        )
    )
    vote_count = int(count_res.scalar() or 0)

    total_res = await session.execute(
        select(func.count(Vote.id)).where(Vote.session_id == vote_session.id)
    )
    total_votes = int(total_res.scalar() or 0)

    return VoteOut(
        session_id=str(vote_session.id),
        outfit_id=str(outfit_id),
        vote_count=vote_count,
        total_votes=total_votes,
    )
