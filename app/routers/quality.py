from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.config import settings
from app.auth.deps import get_current_user_id
from app.models.models import User, WardrobeQualityScore, WardrobeQualitySuggestion
from app.schemas.quality import (
    QualityPreferences,
    QualityPreferencesUpdate,
    QualitySummaryOut,
    QualityScoreOut,
    DimensionScore,
    SuggestionsOut,
    SuggestionOut,
    SuggestionDismissIn,
)
from app.services.quality import QualityEngine

router = APIRouter(prefix="/quality", tags=["quality"])
engine = QualityEngine()


def _score_to_out(score: WardrobeQualityScore, prev: Optional[WardrobeQualityScore] = None) -> QualityScoreOut:
    """Convert DB model to response schema."""
    explanations = score.explanations or {}

    def dim_score(name: str, value: float, weight: float) -> DimensionScore:
        expl = explanations.get(name, {})
        return DimensionScore(
            score=value,
            weight=weight,
            why=expl.get("why", ""),
            confidence=expl.get("confidence", 1.0),
            contributing_factors=expl.get("contributing_factors"),
        )

    # Calculate trend
    trend = None
    trend_delta = None
    if prev:
        delta = score.total_score - prev.total_score
        trend_delta = delta
        if delta > 2:
            trend = "improving"
        elif delta < -2:
            trend = "declining"
        else:
            trend = "stable"

    return QualityScoreOut(
        id=str(score.id),
        total_score=score.total_score,
        confidence=score.confidence,
        versatility=dim_score("versatility", score.versatility_score, settings.QUALITY_WEIGHT_VERSATILITY),
        utilization=dim_score("utilization", score.utilization_score, settings.QUALITY_WEIGHT_UTILIZATION),
        completeness=dim_score("completeness", score.completeness_score, settings.QUALITY_WEIGHT_COMPLETENESS),
        balance=dim_score("balance", score.balance_score, settings.QUALITY_WEIGHT_BALANCE),
        diversity=dim_score("diversity", score.diversity_score, settings.QUALITY_WEIGHT_DIVERSITY),
        items_count=score.items_count,
        outfits_count=score.outfits_count,
        wear_logs_count=score.wear_logs_count,
        computed_at=str(score.computed_at),
        trend=trend,
        trend_delta=trend_delta,
    )


def _suggestion_to_out(sug: WardrobeQualitySuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=str(sug.id),
        suggestion_type=sug.suggestion_type,
        dimension=sug.dimension,
        priority=sug.priority,
        title=sug.title,
        description=sug.description,
        why=sug.why,
        confidence=sug.confidence,
        expected_impact=sug.expected_impact,
        related_item_ids=sug.related_item_ids,
        status=sug.status,
        created_at=str(sug.created_at),
    )


@router.get("/summary", response_model=QualitySummaryOut)
async def get_quality_summary(
    refresh: bool = Query(False, description="Force recompute score"),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Get quality summary including current score, history, and preferences.

    By default returns cached score if recent. Set refresh=true to force recompute.
    """
    # Load user preferences
    user = await session.get(User, user_id)
    prefs_data = (user.quality_preferences if user else None) or {}
    preferences = QualityPreferences(**prefs_data) if prefs_data else QualityPreferences()

    # Get or compute current score
    latest = await engine.get_latest_score(session, user_id)

    if refresh or not latest:
        score, _ = await engine.compute_score(session, user_id)
        latest = score

    # Get history
    history = await engine.get_score_history(session, user_id, limit=10)

    # Find previous score for trend
    prev_score = history[1] if len(history) > 1 else None

    current_out = _score_to_out(latest, prev_score)
    history_out = [_score_to_out(s) for s in history[1:]]  # Exclude current

    return QualitySummaryOut(
        current=current_out,
        history=history_out,
        preferences=preferences,
    )


@router.get("/suggestions", response_model=SuggestionsOut)
async def get_suggestions(
    status: Optional[str] = Query("pending", pattern="^(pending|dismissed|completed|all)$"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get actionable suggestions for improving wardrobe quality."""
    # Get latest score to ensure suggestions exist
    latest = await engine.get_latest_score(session, user_id)
    if not latest:
        # Compute score first
        await engine.compute_score(session, user_id)

    # Query suggestions
    query = select(WardrobeQualitySuggestion).where(
        WardrobeQualitySuggestion.user_id == user_id
    )
    if status != "all":
        query = query.where(WardrobeQualitySuggestion.status == status)
    query = query.order_by(
        WardrobeQualitySuggestion.priority,
        WardrobeQualitySuggestion.created_at.desc()
    ).limit(limit)

    result = await session.execute(query)
    suggestions = list(result.scalars().all())

    # Group by dimension
    by_dimension: dict[str, list[SuggestionOut]] = {}
    suggestion_outs = []
    for sug in suggestions:
        out = _suggestion_to_out(sug)
        suggestion_outs.append(out)
        if sug.dimension not in by_dimension:
            by_dimension[sug.dimension] = []
        by_dimension[sug.dimension].append(out)

    return SuggestionsOut(
        suggestions=suggestion_outs,
        by_dimension=by_dimension,
        total_count=len(suggestion_outs),
    )


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionOut)
async def update_suggestion(
    suggestion_id: UUID,
    payload: SuggestionDismissIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Dismiss or mark a suggestion as completed."""
    sug = await session.get(WardrobeQualitySuggestion, suggestion_id)
    if not sug or str(sug.user_id) != user_id:
        raise HTTPException(status_code=404, detail="suggestion_not_found")

    sug.status = payload.status
    await session.commit()
    await session.refresh(sug)

    return _suggestion_to_out(sug)


@router.get("/preferences", response_model=QualityPreferences)
async def get_preferences(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get user's quality scoring preferences."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    prefs_data = user.quality_preferences or {}
    return QualityPreferences(**prefs_data) if prefs_data else QualityPreferences()


@router.patch("/preferences", response_model=QualityPreferences)
async def update_preferences(
    payload: QualityPreferencesUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update user's quality scoring preferences."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    current = user.quality_preferences or {}
    updates = payload.model_dump(exclude_unset=True)

    # Merge diversity settings
    if "diversity" in updates and updates["diversity"]:
        current_div = current.get("diversity", {})
        current_div.update(updates["diversity"])
        current["diversity"] = current_div

    # Update other settings
    for key in ["refresh_interval_days", "history_retention_days"]:
        if key in updates and updates[key] is not None:
            current[key] = updates[key]

    user.quality_preferences = current
    await session.commit()
    await session.refresh(user)

    return QualityPreferences(**user.quality_preferences)
