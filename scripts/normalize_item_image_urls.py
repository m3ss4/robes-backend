from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import ItemImage
from app.storage.r2 import R2_BUCKET, R2_CDN_BASE


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


async def _run() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        res = await session.execute(select(ItemImage))
        images = res.scalars().all()
        updated = 0
        for img in images:
            key = img.key or _extract_key(img.url or "")
            if not key:
                continue
            if img.key != key:
                img.key = key
                updated += 1
            if R2_CDN_BASE:
                new_url = f"{R2_CDN_BASE}/{key}"
                if img.url != new_url:
                    img.url = new_url
                    updated += 1
        await session.commit()
        print(f"Updated item image URLs: {updated}")


if __name__ == "__main__":
    asyncio.run(_run())
