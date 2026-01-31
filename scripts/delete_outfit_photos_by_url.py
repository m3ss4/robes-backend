from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import Outfit, OutfitPhoto, OutfitPhotoAnalysis, OutfitWearLog
from app.storage.r2 import r2_client, R2_BUCKET, R2_CDN_BASE, object_url


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
    return path


def _photo_urls_for_key(key: str) -> set[str]:
    urls = {object_url(key)}
    if R2_CDN_BASE:
        urls.add(f"{R2_CDN_BASE}/{key}")
    return urls


async def _delete_one(session, url: str) -> None:
    key = _extract_key(url)
    if not key:
        print(f"skip: could not extract key from {url}")
        return

    # delete object from R2
    s3 = r2_client()
    try:
        s3.delete_object(Bucket=R2_BUCKET, Key=key)
        print(f"deleted: r2://{R2_BUCKET}/{key}")
    except Exception as e:
        print(f"warn: failed to delete r2 object for {key}: {e}")

    # delete DB rows
    res = await session.execute(select(OutfitPhoto).where(OutfitPhoto.key == key))
    photo = res.scalar_one_or_none()
    if not photo:
        res = await session.execute(select(OutfitPhoto).where(OutfitPhoto.image_url == url))
        photo = res.scalar_one_or_none()

    if photo:
        res_logs = await session.execute(
            select(OutfitWearLog).where(
                OutfitWearLog.outfit_photo_id == photo.id,
                OutfitWearLog.deleted_at.is_(None),
            )
        )
        logs = res_logs.scalars().all()
        for log in logs:
            log.deleted_at = log.deleted_at or log.created_at
            if not log.source:
                log.source = "photo_deleted"

        for photo_url in _photo_urls_for_key(key) | {url}:
            res_outfits = await session.execute(
                select(Outfit).where(Outfit.primary_image_url == photo_url)
            )
            outfits = res_outfits.scalars().all()
            for outfit in outfits:
                outfit.primary_image_url = None

        await session.execute(
            select(OutfitPhotoAnalysis).where(OutfitPhotoAnalysis.outfit_photo_id == photo.id)
        )
        await session.delete(photo)
        print(f"deleted: outfit_photo {photo.id}")
    else:
        print(f"warn: no outfit_photo row for key {key}")


async def _run(urls: list[str]) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        for url in urls:
            await _delete_one(session, url)
        await session.commit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 scripts/delete_outfit_photos_by_url.py <url1> <url2> ...")
        raise SystemExit(1)
    asyncio.run(_run(sys.argv[1:]))
