from uuid import UUID, uuid4
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.core.db import get_session
from app.auth.deps import get_current_user_id
from app.models.models import SuggestSession, Item
from app.schemas.schemas import Outfit, OutfitSuggestOut
from app.services import llm as llm_service
from app.services.llm.types import ExplainOutfitInput
from app.core.config import settings
import logging
from app.services.outfit_score import score_outfit, fetch_items
from datetime import datetime, timezone

router = APIRouter(prefix="/suggest-sessions", tags=["outfit-sessions"])
logger = logging.getLogger("uvicorn.error")


def _item_descriptors(sel: list[dict], item_lookup: dict[str, Item]) -> list[dict]:
    descs = []
    for s in sel:
        item = item_lookup.get(s["item_id"])
        if not item:
            continue
        descs.append(
            {
                "slot": s["slot"],
                "base_color": item.base_color,
                "pattern": item.pattern,
                "material": item.material,
                "name": item.name or "",
            }
        )
    return descs


@router.post("/{session_id}/rotate", response_model=OutfitSuggestOut)
async def rotate_slot(
    session_id: UUID,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    slot = payload.get("slot")
    direction = payload.get("direction", "next")
    if slot not in {"top", "bottom", "one_piece", "outerwear", "shoes", "bag", "accessory"}:
        raise HTTPException(status_code=400, detail="invalid_slot")

    now = datetime.now(timezone.utc)
    await session.execute(
        delete(SuggestSession).where(
            SuggestSession.user_id == user_id, SuggestSession.expires_at.isnot(None), SuggestSession.expires_at < now
        )
    )

    res = await session.execute(select(SuggestSession).where(SuggestSession.id == session_id, SuggestSession.user_id == user_id))
    sess = res.scalar_one_or_none()
    if not sess or not sess.candidate_map or not sess.cursor:
        raise HTTPException(status_code=404, detail="session_not_found")
    if sess.expires_at and sess.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="session_expired")

    candidate_map = sess.candidate_map
    cursor = sess.cursor
    if slot not in candidate_map or not candidate_map[slot]:
        raise HTTPException(status_code=400, detail="no_candidates_for_slot")

    idx = cursor.get(slot, 0)
    if direction == "next":
        idx = (idx + 1) % len(candidate_map[slot])
    elif direction == "prev":
        idx = (idx - 1) % len(candidate_map[slot])
    cursor[slot] = idx

    # Build item selection from cursor
    selected = []
    for s, ids in candidate_map.items():
        if not ids:
            continue
        sel_idx = cursor.get(s, 0) % len(ids)
        selected.append({"item_id": ids[sel_idx], "slot": s})

    # ensure mandatory shoes
    if not any(i["slot"] == "shoes" for i in selected):
        raise HTTPException(status_code=400, detail="session_missing_shoes")

    metrics = await score_outfit(session, user_id, selected, sess.context or {})
    rationale = metrics.get("explanations", [])
    item_map = await fetch_items(session, user_id, [it["item_id"] for it in selected])
    if settings.LLM_ENABLED:
        try:
            llm_out = await llm_service.explain_outfit(
                ExplainOutfitInput(
                    metrics=metrics,
                    context=sess.context or {},
                    items=_item_descriptors(selected, item_map),
                    prompt_version="p1",
                    compare=False,
                )
            )
            if llm_out.explanations:
                rationale = llm_out.explanations
            logger.info(
                "outfit-rotate-explain llm model=%s cached=%s latency_ms=%s",
                llm_out.usage.model,
                llm_out.usage.cached,
                llm_out.usage.latency_ms,
            )
        except Exception as e:
            logger.warning("outfit-rotate explain llm failed reason=%s", e)
    outfit = Outfit(
        id=str(sess.id),
        score=metrics["total"],
        rationale=rationale,
        slots={s: i["item_id"] for s, i in zip([it["slot"] for it in selected], selected)},
    )
    return OutfitSuggestOut(outfits=[outfit])
