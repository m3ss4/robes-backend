from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, func, delete
from uuid import uuid4
from datetime import datetime, timedelta, timezone, date
import logging
from app.schemas.schemas import (
    OutfitSuggestIn,
    OutfitSuggestOut,
    Outfit,
    OutfitCreate,
    OutfitOut,
    WearLogIn,
    WearLogOut,
    WearLogDeleteIn,
    ScoreRequest,
    ScoreOut,
    OutfitFeedbackIn,
    OutfitFeedbackOut,
    OutfitDecisionIn,
)
from app.auth.deps import get_current_user_id
from app.core.db import get_session
from app.models.models import Outfit as OutfitModel, OutfitItem, OutfitWearLog, OutfitWearLogItem, OutfitRevision
from app.core.tags import clamp_limits
from typing import List, Optional
from app.services.outfit_score import score_outfit as compute_outfit_score
from app.models.models import Item, SuggestSession
from app.services import llm as llm_service
from app.services.llm.types import ExplainOutfitInput
from app.core.config import settings

router = APIRouter(prefix="/outfits", tags=["outfits"])
logger = logging.getLogger("uvicorn.error")

def _slot_for_item(item: Item) -> str:
    kind = item.kind
    if kind == "onepiece":
        return "one_piece"
    if kind == "outerwear":
        return "outerwear"
    if kind == "footwear":
        return "shoes"
    if kind == "accessory":
        return "accessory"
    if kind == "top":
        return "top"
    if kind == "bottom":
        return "bottom"
    return "accessory"


def _filtered_candidates(items: list[Item], ctx: dict) -> dict[str, list[str]]:
    event = (ctx.get("event") or "").lower()
    season = (ctx.get("season") or "").lower()
    cmap: dict[str, list[tuple[int, str]]] = {}
    for it in items:
        slot = _slot_for_item(it)
        score = 0
        if event and it.event_tags and event in [e.lower() for e in it.event_tags]:
            score += 2
        if season and it.season_tags and season in [s.lower() for s in it.season_tags]:
            score += 1
        if it.base_color in {"black", "white", "navy", "gray"}:
            score += 1
        cmap.setdefault(slot, []).append((score, str(it.id)))
    # sort by score desc, then id
    out: dict[str, list[str]] = {}
    for slot, vals in cmap.items():
        vals.sort(key=lambda x: x[0], reverse=True)
        out[slot] = [v[1] for v in vals[:20]]
    return out


def _pattern_ok(sel: list[dict], item_lookup: dict[str, Item]) -> bool:
    patterned = 0
    for s in sel:
        item = item_lookup.get(s["item_id"])
        if item and item.pattern and item.pattern != "solid":
            patterned += 1
    return patterned <= 1


def _normalize_feel_tags(tags: list[str]) -> list[str]:
    cleaned = []
    for tag in tags or []:
        if not tag:
            continue
        trimmed = tag.strip()
        if trimmed:
            cleaned.append(trimmed[:32])
    return cleaned[:12]


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


@router.post("/suggest", response_model=OutfitSuggestOut)
async def suggest_outfits(
    ctx: OutfitSuggestIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    # cleanup expired sessions for this user
    now = datetime.now(timezone.utc)
    await session.execute(delete(SuggestSession).where(SuggestSession.user_id == user_id, SuggestSession.expires_at.isnot(None), SuggestSession.expires_at < now))

    # build candidate pools by slot
    res = await session.execute(select(Item).where(Item.user_id == user_id))
    items = res.scalars().all()
    ctx_dict = ctx.model_dump()
    candidate_map = _filtered_candidates(items, ctx_dict)

    if not candidate_map.get("shoes"):
        return OutfitSuggestOut(outfits=[])

    # build top combos by simple greedy search with limits
    combos = []
    tops = candidate_map.get("one_piece") or candidate_map.get("top", [])
    bottoms = [] if candidate_map.get("one_piece") else candidate_map.get("bottom", [])
    shoes = candidate_map["shoes"]
    outer = candidate_map.get("outerwear", [])

    def add_combo(sel: list[dict]):
        combos.append(sel)

    shoe_limit = 8
    per_slot_limit = 15
    item_lookup = {str(it.id): it for it in items}
    for s in shoes[:shoe_limit]:
        if candidate_map.get("one_piece"):
            for op in candidate_map["one_piece"][:per_slot_limit]:
                sel = [{"item_id": op, "slot": "one_piece"}, {"item_id": s, "slot": "shoes"}]
                if outer:
                    sel.append({"item_id": outer[0], "slot": "outerwear"})
                if _pattern_ok(sel, item_lookup):
                    add_combo(sel)
        else:
            for t in candidate_map.get("top", [])[:per_slot_limit]:
                for b in bottoms[:per_slot_limit]:
                    sel = [{"item_id": t, "slot": "top"}, {"item_id": b, "slot": "bottom"}, {"item_id": s, "slot": "shoes"}]
                    if outer:
                        sel.append({"item_id": outer[0], "slot": "outerwear"})
                    if _pattern_ok(sel, item_lookup):
                        add_combo(sel)
        if len(combos) > 40:
            break

    scored = []
    for sel in combos:
        m = await compute_outfit_score(session, user_id, sel, ctx.model_dump())
        scored.append((m["total"], sel, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:3]

    # seed session for carousel
    # cursor based on best combo (first)
    best_sel = top[0][1] if top else []
    cursor = {}
    for s, ids in candidate_map.items():
        if not ids:
            continue
        # find index of selected item in this slot if present
        selected_id = next((x["item_id"] for x in best_sel if x["slot"] == s), None)
        idx = ids.index(selected_id) if selected_id in ids else 0
        cursor[s] = idx

    sess = SuggestSession(
        id=uuid4(),
        user_id=user_id,
        context=ctx.model_dump(),
        candidate_map=candidate_map,
        cursor=cursor,
        model_info={"rules_version": "r1", "prompt_version": "p1", "features_version": "v1"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    session.add(sess)
    await session.flush()

    outfits_out = []
    for total, sel, m in top:
        rationale = m.get("explanations", [])
        # Optional LLM explanation / tiebreak note
        if settings.LLM_ENABLED:
            try:
                llm_out = await llm_service.explain_outfit(
                    ExplainOutfitInput(
                        metrics=m,
                        context=ctx_dict,
                        items=_item_descriptors(sel, item_lookup),
                        prompt_version="p1",
                        compare=False,
                    )
                )
                if llm_out.explanations:
                    rationale = llm_out.explanations
                logger.info(
                    "outfit-explain llm model=%s cached=%s latency_ms=%s",
                    llm_out.usage.model,
                    llm_out.usage.cached,
                    llm_out.usage.latency_ms,
                )
            except Exception as e:
                logger.warning("outfit-explain llm failed reason=%s", e)
        outfit = OutfitModel(
            id=uuid4(),
            user_id=user_id,
            status="suggested_pending",
            source="robes",
            metrics=m,
        )
        session.add(outfit)
        await session.flush()
        for s in sel:
            session.add(OutfitItem(id=uuid4(), outfit_id=outfit.id, item_id=s["item_id"], slot=s["slot"], position=0))
        outfits_out.append(Outfit(id=str(outfit.id), score=m["total"], rationale=rationale, slots={s["slot"]: s["item_id"] for s in sel}))

    await session.commit()
    return OutfitSuggestOut(session_id=str(sess.id), outfits=outfits_out)


@router.post(
    "",
    response_model=OutfitOut,
    summary="Create outfit",
)
async def create_outfit(
    payload: OutfitCreate = Body(
        ...,
        examples={
            "top_bottom": {
                "summary": "Top + Bottom + Shoes",
                "value": {
                    "name": "Friday casual",
                    "notes": "Navy tee and jeans",
                    "items": [
                        {"item_id": "uuid-top", "slot": "top", "position": 0},
                        {"item_id": "uuid-bottom", "slot": "bottom", "position": 1},
                        {"item_id": "uuid-shoes", "slot": "shoes", "position": 2},
                    ],
                },
            },
            "one_piece": {
                "summary": "One-piece + Shoes + Outerwear",
                "value": {
                    "name": "Winter dress",
                    "items": [
                        {"item_id": "uuid-dress", "slot": "one_piece", "position": 0},
                        {"item_id": "uuid-shoes", "slot": "shoes", "position": 1},
                        {"item_id": "uuid-coat", "slot": "outerwear", "position": 2},
                    ],
                },
            },
        },
    ),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a manual outfit.
    Defaults: status->"active", source->"manual", attributes->{}, metrics computed if omitted.
    Requires at least 2 unique items; one_piece cannot mix with top/bottom. Positions are normalized to be deterministic.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="items_required")
    if len(payload.items) < 2:
        raise HTTPException(status_code=422, detail="at_least_two_items_required")
    if len({i.item_id for i in payload.items}) != len(payload.items):
        raise HTTPException(status_code=422, detail="duplicate_item_ids")
    # Basic slot validation: one_piece xor (top+bottom)
    slots = {i.slot for i in payload.items}
    if "one_piece" in slots and ("top" in slots or "bottom" in slots):
        raise HTTPException(status_code=422, detail="one_piece_conflict")

    # positions: ensure non-negative and fill defaults deterministically
    normalized_items = []
    pos_counter = 0
    for oi in payload.items:
        if oi.position is not None and oi.position < 0:
            raise HTTPException(status_code=422, detail="position_must_be_non_negative")
        position = oi.position if oi.position is not None else pos_counter
        pos_counter += 1
        normalized_items.append({"item_id": oi.item_id, "slot": oi.slot, "position": position})

    # Ownership and active check
    res_items = await session.execute(select(Item).where(Item.user_id == user_id, Item.id.in_([i["item_id"] for i in normalized_items])))
    found = {str(i.id): i for i in res_items.scalars().all()}
    if len(found) != len(normalized_items):
        raise HTTPException(status_code=422, detail="item_not_owned_or_missing")
    for i in normalized_items:
        item = found.get(i["item_id"])
        if item and hasattr(item, "is_active") and item.is_active is False:
            raise HTTPException(status_code=422, detail="item_inactive")

    computed_metrics = payload.metrics or await compute_outfit_score(session, user_id, normalized_items, payload.attributes or {})
    outfit = OutfitModel(
        id=uuid4(),
        user_id=user_id,
        name=payload.name,
        status=payload.status or "active",
        notes=payload.notes,
        attributes=payload.attributes or {},
        metrics=computed_metrics,
        source=payload.source or "manual",
    )
    session.add(outfit)
    await session.flush()

    for oi in normalized_items:
        session.add(
            OutfitItem(
                id=uuid4(),
                outfit_id=outfit.id,
                item_id=oi["item_id"],
                slot=oi["slot"],
                position=oi["position"] or 0,
            )
        )
    await session.commit()
    await session.refresh(outfit)
    return await _outfit_out(outfit, session)


async def _outfit_out(outfit: OutfitModel, session: AsyncSession) -> OutfitOut:
    if not outfit.items:
        res = await session.execute(select(OutfitItem).where(OutfitItem.outfit_id == outfit.id))
        outfit.items = res.scalars().all()
    # Order items by position then slot
    ordered = sorted(outfit.items, key=lambda oi: (oi.position or 0, oi.slot))
    item_ids = [oi.item_id for oi in ordered]
    items_map = {}
    if item_ids:
        res_items = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        items_map = {i.id: i for i in res_items.scalars().all()}
    items_detail = []
    for oi in ordered:
        item = items_map.get(oi.item_id)
        items_detail.append(
            {
                "item_id": str(oi.item_id),
                "slot": oi.slot,
                "position": oi.position or 0,
                "type": item.item_type if item else None,
                "category": item.category if item else None,
                "base_color": item.base_color if item else None,
            }
        )
    return OutfitOut(
        id=str(outfit.id),
        name=outfit.name,
        status=outfit.status,
        notes=outfit.notes,
        feedback=outfit.feedback,
        attributes=outfit.attributes,
        metrics=outfit.metrics,
        source=outfit.source,
        primary_image_url=outfit.primary_image_url,
        created_at=str(outfit.created_at) if outfit.created_at else None,
        updated_at=str(outfit.updated_at) if getattr(outfit, "updated_at", None) else None,
        items=[{"item_id": str(oi.item_id), "slot": oi.slot, "position": oi.position} for oi in ordered],
        items_detail=items_detail,
    )


@router.get("", response_model=List[OutfitOut])
async def list_outfits(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    q = select(OutfitModel).where(OutfitModel.user_id == user_id).order_by(OutfitModel.created_at.desc())
    if status:
        q = q.where(OutfitModel.status == status)
    res = await session.execute(q)
    outfits = res.scalars().all()
    return [await _outfit_out(o, session) for o in outfits]


@router.get("/{outfit_id}", response_model=OutfitOut)
async def get_outfit(outfit_id: str, session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id)):
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    return await _outfit_out(outfit, session)


@router.patch("/{outfit_id}", response_model=OutfitOut)
async def update_outfit(
    outfit_id: str,
    payload: OutfitCreate,  # reuse structure for simplicity
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    if payload.name is not None:
        outfit.name = payload.name
    if payload.notes is not None:
        outfit.notes = payload.notes
    if payload.status is not None:
        outfit.status = payload.status
    if payload.attributes is not None:
        outfit.attributes = payload.attributes
    recalc_needed = False
    if payload.metrics is not None:
        outfit.metrics = payload.metrics
    else:
        recalc_needed = True
    if payload.source is not None:
        outfit.source = payload.source
    if payload.items is not None:
        # replace items
        await session.execute(
            OutfitItem.__table__.delete().where(OutfitItem.outfit_id == outfit.id)
        )
        for oi in payload.items:
            session.add(
                OutfitItem(
                    id=uuid4(),
                    outfit_id=outfit.id,
                    item_id=oi.item_id,
                    slot=oi.slot,
                    position=oi.position or 0,
                )
            )
    if recalc_needed or payload.items is not None:
        items_for_score = payload.items if payload.items is not None else [
            {"item_id": str(oi.item_id), "slot": oi.slot, "position": oi.position} for oi in outfit.items
        ]
        outfit.metrics = await compute_outfit_score(session, user_id, [i if isinstance(i, dict) else i.model_dump() for i in items_for_score], outfit.attributes or {})

    await session.commit()
    await session.refresh(outfit)
    return await _outfit_out(outfit, session)


@router.patch("/{outfit_id}/feedback", response_model=OutfitFeedbackOut)
async def update_outfit_feedback(
    outfit_id: str,
    payload: OutfitFeedbackIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    data = payload.model_dump(exclude_unset=True)
    if "feel_tags" in data and data["feel_tags"] is not None:
        data["feel_tags"] = _normalize_feel_tags(data["feel_tags"])
    if data:
        feedback = dict(outfit.feedback or {})
        feedback.update(data)
        outfit.feedback = feedback
        await session.commit()
        await session.refresh(outfit)
    return OutfitFeedbackOut(
        outfit_id=str(outfit.id),
        feedback=OutfitFeedbackIn(**(outfit.feedback or {})),
        updated_at=str(outfit.updated_at) if getattr(outfit, "updated_at", None) else None,
    )


@router.delete("/{outfit_id}", status_code=204)
async def delete_outfit(
    outfit_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    await session.delete(outfit)
    await session.commit()
    return None


@router.post("/{outfit_id}/wear-log", response_model=WearLogOut)
async def log_wear(
    outfit_id: str,
    payload: WearLogIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Log an outfit wear. Idempotent per day (Europe/London). Duplicate logs for same day return existing.
    """
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    # snapshot items
    items_snapshot = [{"item_id": str(oi.item_id), "slot": oi.slot, "position": oi.position} for oi in outfit.items]
    worn_at, worn_date = _compute_worn_times(payload.worn_at)

    # idempotent per day
    existing_q = await session.execute(
        select(OutfitWearLog).where(
            OutfitWearLog.user_id == user_id,
            OutfitWearLog.outfit_id == outfit_id,
            OutfitWearLog.worn_date == worn_date,
            OutfitWearLog.deleted_at.is_(None),
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing:
        return WearLogOut(
            id=str(existing.id),
            outfit_id=str(existing.outfit_id),
            worn_at=str(existing.worn_at),
            worn_date=str(existing.worn_date),
            source=existing.source,
            event=existing.event,
            location=existing.location,
            season=existing.season,
            mood=existing.mood,
            notes=existing.notes,
        )
    # increment rev_no
    rev_no = 1
    res_rev = await session.execute(select(func.max(OutfitRevision.rev_no)).where(OutfitRevision.outfit_id == outfit.id))
    max_rev = res_rev.scalar_one_or_none()
    if max_rev:
        rev_no = max_rev + 1
    rev = OutfitRevision(
        id=uuid4(),
        outfit_id=outfit.id,
        rev_no=rev_no,
        items_snapshot=items_snapshot,
        attributes_snapshot=outfit.attributes,
        metrics_snapshot=outfit.metrics,
    )
    session.add(rev)
    await session.flush()
    log = OutfitWearLog(
        id=uuid4(),
        user_id=user_id,
        outfit_id=outfit.id,
        outfit_revision_id=rev.id,
        worn_at=worn_at,
        worn_date=worn_date,
        source=payload.source,
        event=payload.event,
        location=payload.location,
        weather=payload.weather,
        season=payload.season,
        mood=payload.mood,
        notes=payload.notes,
    )
    session.add(log)
    try:
        await session.flush()
    except Exception:
        await session.rollback()
        # race: try existing
        existing_q = await session.execute(
            select(OutfitWearLog).where(
                OutfitWearLog.user_id == user_id,
                OutfitWearLog.outfit_id == outfit_id,
                OutfitWearLog.worn_date == worn_date,
                OutfitWearLog.deleted_at.is_(None),
            )
        )
        existing = existing_q.scalar_one_or_none()
        if existing:
            return WearLogOut(
                id=str(existing.id),
                outfit_id=str(existing.outfit_id),
                worn_at=str(existing.worn_at),
                worn_date=str(existing.worn_date),
                source=existing.source,
                event=existing.event,
                location=existing.location,
                season=existing.season,
                mood=existing.mood,
                notes=existing.notes,
            )
        raise
    # child items
    for oi in outfit.items:
        session.add(OutfitWearLogItem(wear_log_id=log.id, item_id=oi.item_id, slot=oi.slot))
    await session.commit()
    return WearLogOut(
        id=str(log.id),
        outfit_id=str(outfit.id),
        worn_at=str(log.worn_at),
        worn_date=str(log.worn_date),
        source=log.source,
        event=log.event,
        location=log.location,
        season=log.season,
        mood=log.mood,
        notes=log.notes,
    )


@router.patch("/{outfit_id}/wear-log/{log_id}", status_code=204)
async def delete_wear_log_entry(
    outfit_id: str,
    log_id: str,
    payload: WearLogDeleteIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    data = payload.model_dump(exclude_unset=True)
    if data.get("deleted") is not True and data.get("source") != "deleted":
        raise HTTPException(status_code=400, detail="invalid_delete_request")
    res = await session.execute(
        select(OutfitWearLog).where(
            OutfitWearLog.id == log_id,
            OutfitWearLog.outfit_id == outfit_id,
            OutfitWearLog.user_id == user_id,
        )
    )
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="wear_log_not_found")
    if log.deleted_at is None:
        log.deleted_at = datetime.now(timezone.utc)
        if data.get("source"):
            log.source = data["source"]
        elif data.get("deleted") is True and not log.source:
            log.source = "deleted"
        await session.commit()
    return None


@router.get("/{outfit_id}/history", response_model=List[WearLogOut])
async def outfit_history(
    outfit_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(
        select(OutfitWearLog)
        .where(
            OutfitWearLog.outfit_id == outfit_id,
            OutfitWearLog.user_id == user_id,
            OutfitWearLog.deleted_at.is_(None),
        )
        .order_by(OutfitWearLog.worn_at.desc())
    )
    logs = res.scalars().all()
    return [
        WearLogOut(
            id=str(l.id),
            outfit_id=str(l.outfit_id),
            worn_at=str(l.worn_at),
            worn_date=str(getattr(l, "worn_date", None)) if getattr(l, "worn_date", None) else None,
            source=l.source,
            event=l.event,
            location=l.location,
            season=l.season,
            mood=l.mood,
            notes=l.notes,
        )
        for l in logs
    ]


@router.post("/score", response_model=ScoreOut)
async def score_outfit_endpoint(
    payload: ScoreRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    metrics = await compute_outfit_score(session, user_id, [i.model_dump() for i in payload.items], payload.context or {})
    return ScoreOut(metrics=metrics)


@router.post("/{outfit_id}/decision")
async def outfit_decision(
    outfit_id: str,
    payload: OutfitDecisionIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    res = await session.execute(select(OutfitModel).where(OutfitModel.id == outfit_id, OutfitModel.user_id == user_id))
    outfit = res.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="outfit_not_found")
    if payload.decision == "accept":
        outfit.status = "suggested_accepted"
    elif payload.decision == "reject":
        outfit.status = "suggested_rejected"
    await session.commit()
    return {"ok": True, "status": outfit.status}


def _compute_worn_times(worn_at_str: Optional[str]) -> tuple[datetime, datetime.date]:
    from zoneinfo import ZoneInfo

    tz_london = ZoneInfo("Europe/London")
    if worn_at_str:
        try:
            dt = datetime.fromisoformat(worn_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    worn_date = dt.astimezone(tz_london).date()
    return dt, worn_date
