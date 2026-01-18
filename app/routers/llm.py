from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.deps import get_current_user_id
from app.core.db import get_session
from app.models.models import Item
from app.schemas.schemas import AskUserItemsIn, AskUserItemsOut
from app.services import llm as llm_service
from app.services.llm.types import AskUserItemsInput

router = APIRouter(prefix="/llm", tags=["llm"])


def _item_payload(item: Item) -> dict:
    return {
        "id": str(item.id),
        "category": item.category,
        "kind": item.kind,
        "status": item.status,
        "type": item.item_type,
        "fit": item.fit,
        "fabric_kind": item.fabric_kind,
        "pattern": item.pattern,
        "tone": item.tone,
        "layer_role": item.layer_role,
        "name": item.name,
        "brand": item.brand,
        "base_color": item.base_color,
        "material": item.material,
        "warmth": item.warmth,
        "formality": item.formality,
        "style_tags": item.style_tags or [],
        "event_tags": item.event_tags or [],
        "season_tags": item.season_tags or [],
        "attribute_sources": item.attribute_sources or {},
    }


@router.post("/ask", response_model=AskUserItemsOut)
async def ask_items(
    payload: AskUserItemsIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(select(Item).where(Item.user_id == user_id))
    items = res.scalars().all()
    llm_payload = AskUserItemsInput(
        question=payload.question,
        items=[_item_payload(i) for i in items],
    )
    out = await llm_service.ask_user_items(llm_payload)
    return AskUserItemsOut(answer=out.answer, usage=out.usage.model_dump())
