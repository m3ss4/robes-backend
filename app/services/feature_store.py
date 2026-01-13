from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ItemImageFeatures, ItemImage
from app.core.config import settings


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def get_for_images(session: AsyncSession, image_ids: List[str]) -> Dict[str, ItemImageFeatures]:
    if not image_ids:
        return {}
    res = await session.execute(
        select(ItemImageFeatures)
        .where(ItemImageFeatures.image_id.in_(image_ids))
        .order_by(ItemImageFeatures.image_id, ItemImageFeatures.computed_at.desc())
    )
    out: Dict[str, ItemImageFeatures] = {}
    for row in res.scalars().all():
        key = str(row.image_id)
        if key not in out:
            out[key] = row
    return out


async def get_latest_for_item(session: AsyncSession, item_id: str) -> List[ItemImageFeatures]:
    res = await session.execute(select(ItemImage.id).where(ItemImage.item_id == item_id))
    image_ids = [r[0] for r in res.fetchall()]
    feats = await get_for_images(session, image_ids)
    return list(feats.values())


async def wait_for_any(session: AsyncSession, image_ids: List[str], timeout_ms: int = 800, poll_ms: int = 100) -> Dict[str, ItemImageFeatures]:
    if not image_ids:
        return {}
    end = asyncio.get_event_loop().time() + timeout_ms / 1000.0
    while True:
        found = await get_for_images(session, image_ids)
        if found:
            return found
        if asyncio.get_event_loop().time() >= end:
            return {}
        await asyncio.sleep(poll_ms / 1000.0)


async def upsert(session: AsyncSession, image_id: str, payload: Dict[str, Any]) -> None:
    stmt = (
        insert(ItemImageFeatures)
        .values(image_id=image_id, **payload)
        .on_conflict_do_update(
            index_elements=[ItemImageFeatures.image_id, ItemImageFeatures.features_version],
            set_=payload,
        )
    )
    await session.execute(stmt)


async def by_hash(session: AsyncSession, image_sha256: str) -> Optional[ItemImageFeatures]:
    res = await session.execute(
        select(ItemImageFeatures)
        .where(ItemImageFeatures.image_sha256 == image_sha256, ItemImageFeatures.features_version == settings.IMGPROC_FEATURES_VERSION)
        .order_by(ItemImageFeatures.computed_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()
