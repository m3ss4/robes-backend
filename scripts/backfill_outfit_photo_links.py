from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import Outfit, OutfitPhoto, OutfitWearLog
from app.storage.r2 import object_url, R2_BUCKET, R2_CDN_BASE


def _extract_key(url: str) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(url).path.lstrip("/")
    except Exception:
        return None
    if not path:
        return None
    if R2_BUCKET and path.startswith(f"{R2_BUCKET}/"):
        return path[len(R2_BUCKET) + 1 :]
    if path.startswith("u/"):
        return path
    u_idx = path.find("u/")
    if u_idx >= 0:
        return path[u_idx:]
    photos_idx = path.find("outfits/photos/")
    if photos_idx >= 0:
        return path[photos_idx - 2 :] if photos_idx >= 2 else path[photos_idx:]
    return path


def _photo_urls(photo: OutfitPhoto) -> set[str]:
    urls = set()
    if photo.image_url:
        urls.add(photo.image_url)
    if photo.key:
        urls.add(object_url(photo.key))
        if R2_CDN_BASE:
            urls.add(f"{R2_CDN_BASE}/{photo.key}")
    return urls


async def _run() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        res = await session.execute(select(OutfitPhoto))
        photos = res.scalars().all()

        url_map: dict[tuple[str, str], str] = {}
        key_map: dict[tuple[str, str], str] = {}
        for photo in photos:
            user_id = str(photo.user_id)
            for url in _photo_urls(photo):
                url_map[(user_id, url)] = str(photo.id)
            if photo.key:
                key_map[(user_id, photo.key)] = str(photo.id)

        res = await session.execute(select(Outfit).where(Outfit.primary_image_url.is_not(None)))
        outfits = res.scalars().all()
        updated_logs = 0
        for outfit in outfits:
            user_id = str(outfit.user_id)
            url = outfit.primary_image_url or ""
            photo_id = url_map.get((user_id, url))
            if not photo_id:
                key = _extract_key(url)
                if key:
                    photo_id = key_map.get((user_id, key))
            if not photo_id:
                continue

            res_logs = await session.execute(
                select(OutfitWearLog).where(
                    OutfitWearLog.outfit_id == outfit.id,
                    OutfitWearLog.outfit_photo_id.is_(None),
                )
            )
            logs = res_logs.scalars().all()
            for log in logs:
                log.outfit_photo_id = photo_id
                updated_logs += 1

        await session.commit()
        print(f"Backfill complete. Updated wear logs: {updated_logs}")


if __name__ == "__main__":
    asyncio.run(_run())
