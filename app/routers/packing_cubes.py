from __future__ import annotations

from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user_id
from app.core.db import get_session
from app.models.models import Item, ItemImage, PackingCube, PackingCubeItem
from app.schemas.schemas import (
    PackingCubeIn,
    PackingCubeOut,
    PackingCubeItemIn,
    PackingCubeItemOut,
    PackingCubeDetailOut,
    PackingCubeOwnershipOut,
)
from app.storage.r2 import object_url, presign_get, R2_CDN_BASE


router = APIRouter(prefix="/packing-cubes", tags=["packing-cubes"])


def _public_image_url(key: str, bucket: str | None) -> str:
    if R2_CDN_BASE:
        return f"{R2_CDN_BASE}/{key}"
    return presign_get(key, bucket=bucket)


def _validate_cube_payload(payload: PackingCubeIn) -> tuple[str | None, list[str] | None]:
    location = payload.location
    if payload.type == "physical":
        if not location:
            raise HTTPException(status_code=400, detail="location_required")
    else:
        location = None
    weather_tags = payload.weather_tags or None
    return location, weather_tags


async def _physical_owner(session: AsyncSession, user_id: str, item_id: str, cube_id: str | None) -> str | None:
    conditions = [
        PackingCube.user_id == user_id,
        PackingCube.cube_type == "physical",
        PackingCubeItem.item_id == item_id,
    ]
    if cube_id:
        conditions.append(PackingCubeItem.cube_id != cube_id)
    res = await session.execute(
        select(PackingCubeItem.cube_id)
        .join(PackingCube, PackingCube.id == PackingCubeItem.cube_id)
        .where(*conditions)
        .limit(1)
    )
    row = res.first()
    return str(row[0]) if row else None


@router.get("", response_model=list[PackingCubeOut])
async def list_cubes(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(
        select(PackingCube, func.count(PackingCubeItem.id))
        .outerjoin(PackingCubeItem, PackingCubeItem.cube_id == PackingCube.id)
        .where(PackingCube.user_id == user_id)
        .group_by(PackingCube.id)
        .order_by(PackingCube.created_at.desc())
    )
    rows = res.all()
    return [
        PackingCubeOut(
            id=str(cube.id),
            name=cube.name,
            type=cube.cube_type,
            weather_tags=cube.weather_tags or [],
            location=cube.location,
            item_count=int(count or 0),
            created_at=str(cube.created_at) if cube.created_at else None,
            updated_at=str(cube.updated_at) if cube.updated_at else None,
        )
        for cube, count in rows
    ]


@router.get("/physical-ownership", response_model=PackingCubeOwnershipOut)
async def physical_ownership(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(
        select(PackingCubeItem.item_id, PackingCubeItem.cube_id)
        .join(PackingCube, PackingCube.id == PackingCubeItem.cube_id)
        .where(
            PackingCube.user_id == user_id,
            PackingCube.cube_type == "physical",
        )
    )
    ownership = {str(row[0]): str(row[1]) for row in res.all()}
    return PackingCubeOwnershipOut(ownership=ownership)


@router.post("", response_model=PackingCubeOut)
async def create_cube(
    payload: PackingCubeIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    location, weather_tags = _validate_cube_payload(payload)
    cube = PackingCube(
        id=uuid4(),
        user_id=user_id,
        name=payload.name,
        cube_type=payload.type,
        weather_tags=weather_tags,
        location=location,
    )
    session.add(cube)
    await session.commit()
    await session.refresh(cube)
    return PackingCubeOut(
        id=str(cube.id),
        name=cube.name,
        type=cube.cube_type,
        weather_tags=cube.weather_tags or [],
        location=cube.location,
        item_count=0,
        created_at=str(cube.created_at) if cube.created_at else None,
        updated_at=str(cube.updated_at) if cube.updated_at else None,
    )


@router.patch("/{cube_id}", response_model=PackingCubeOut)
async def update_cube(
    cube_id: UUID,
    payload: PackingCubeIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    cube = await session.get(PackingCube, cube_id)
    if not cube or str(cube.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="cube_not_found")
    location, weather_tags = _validate_cube_payload(payload)
    cube.name = payload.name
    cube.cube_type = payload.type
    cube.weather_tags = weather_tags
    cube.location = location
    await session.commit()
    await session.refresh(cube)
    res = await session.execute(
        select(func.count(PackingCubeItem.id)).where(PackingCubeItem.cube_id == cube.id)
    )
    count = res.scalar_one_or_none() or 0
    return PackingCubeOut(
        id=str(cube.id),
        name=cube.name,
        type=cube.cube_type,
        weather_tags=cube.weather_tags or [],
        location=cube.location,
        item_count=int(count),
        created_at=str(cube.created_at) if cube.created_at else None,
        updated_at=str(cube.updated_at) if cube.updated_at else None,
    )


@router.delete("/{cube_id}", status_code=204)
async def delete_cube(
    cube_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    cube = await session.get(PackingCube, cube_id)
    if not cube or str(cube.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="cube_not_found")
    await session.delete(cube)
    await session.commit()
    return None


@router.get("/{cube_id}", response_model=PackingCubeDetailOut)
async def get_cube(
    cube_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    cube = await session.get(PackingCube, cube_id)
    if not cube or str(cube.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="cube_not_found")
    res = await session.execute(
        select(Item, PackingCubeItem)
        .join(PackingCubeItem, PackingCubeItem.item_id == Item.id)
        .where(PackingCubeItem.cube_id == cube.id)
    )
    items = []
    for item, _ in res.all():
        image_url = None
        res_img = await session.execute(
            select(ItemImage).where(ItemImage.item_id == item.id).order_by(ItemImage.created_at.desc()).limit(1)
        )
        img = res_img.scalar_one_or_none()
        if img:
            if img.key:
                image_url = _public_image_url(img.key, img.bucket)
            elif img.url:
                image_url = img.url
        items.append(
            PackingCubeItemOut(
                item_id=str(item.id),
                name=item.name,
                category=item.category,
                type=item.item_type,
                image_url=image_url,
            )
        )
    return PackingCubeDetailOut(
        id=str(cube.id),
        name=cube.name,
        type=cube.cube_type,
        weather_tags=cube.weather_tags or [],
        location=cube.location,
        items=items,
    )


@router.post("/{cube_id}/items", status_code=204)
async def add_item_to_cube(
    cube_id: UUID,
    payload: PackingCubeItemIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    cube = await session.get(PackingCube, cube_id)
    if not cube or str(cube.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="cube_not_found")
    item = await session.get(Item, payload.item_id)
    if not item or str(item.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="item_not_found")

    if cube.cube_type == "physical":
        owner = await _physical_owner(session, user_id, payload.item_id, str(cube.id))
        if owner:
            raise HTTPException(status_code=400, detail="item_already_in_physical_cube")

    res = await session.execute(
        select(PackingCubeItem).where(
            PackingCubeItem.cube_id == cube.id,
            PackingCubeItem.item_id == payload.item_id,
        )
    )
    existing = res.scalar_one_or_none()
    if not existing:
        session.add(PackingCubeItem(id=uuid4(), cube_id=cube.id, item_id=item.id))
        await session.commit()
    return None


@router.delete("/{cube_id}/items/{item_id}", status_code=204)
async def remove_item_from_cube(
    cube_id: UUID,
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    cube = await session.get(PackingCube, cube_id)
    if not cube or str(cube.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="cube_not_found")
    res = await session.execute(
        select(PackingCubeItem).where(
            PackingCubeItem.cube_id == cube.id,
            PackingCubeItem.item_id == item_id,
        )
    )
    link = res.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="item_not_in_cube")
    await session.delete(link)
    await session.commit()
    return None
