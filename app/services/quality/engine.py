from typing import Optional, Tuple, List
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.models import (
    Item, Outfit, OutfitWearLog, OutfitWearLogItem, ItemWearLog, User,
    WardrobeQualityScore, WardrobeQualitySuggestion,
)
from .types import ScoringContext, DimensionResult
from .scorers import (
    VersatilityScorer,
    UtilizationScorer,
    CompletenessScorer,
    BalanceScorer,
    DiversityScorer,
)
from .suggestions import SuggestionGenerator


class QualityEngine:
    """Main engine for computing wardrobe quality scores."""

    def __init__(self):
        self.scorers = [
            (VersatilityScorer(), settings.QUALITY_WEIGHT_VERSATILITY),
            (UtilizationScorer(), settings.QUALITY_WEIGHT_UTILIZATION),
            (CompletenessScorer(), settings.QUALITY_WEIGHT_COMPLETENESS),
            (BalanceScorer(), settings.QUALITY_WEIGHT_BALANCE),
            (DiversityScorer(), settings.QUALITY_WEIGHT_DIVERSITY),
        ]
        self.suggestion_generator = SuggestionGenerator()

    async def compute_score(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        persist: bool = True,
    ) -> Tuple[WardrobeQualityScore, List[WardrobeQualitySuggestion]]:
        """Compute quality score for a user's wardrobe."""

        # Load user preferences
        user = await session.get(User, user_id)
        prefs = (user.quality_preferences if user else None) or {}
        diversity_config = prefs.get("diversity", {
            "colors": settings.QUALITY_DIVERSITY_COLORS_DEFAULT,
            "patterns": settings.QUALITY_DIVERSITY_PATTERNS_DEFAULT,
            "seasons": settings.QUALITY_DIVERSITY_SEASONS_DEFAULT,
            "styles": settings.QUALITY_DIVERSITY_STYLES_DEFAULT,
        })

        # Load wardrobe data
        ctx = await self._load_context(session, user_id, diversity_config)

        # Compute dimension scores
        dimension_results: dict[str, Tuple[DimensionResult, float]] = {}
        total_score = 0.0
        total_confidence = 0.0
        explanations = {}

        for scorer, weight in self.scorers:
            result = scorer.score(ctx)
            dimension_results[scorer.dimension_name] = (result, weight)
            total_score += result.score * weight
            total_confidence += result.confidence * weight
            explanations[scorer.dimension_name] = {
                "why": result.why,
                "confidence": result.confidence,
                "contributing_factors": result.contributing_factors,
            }

        # Create score record
        score_record = WardrobeQualityScore(
            user_id=user_id,
            total_score=total_score,
            versatility_score=dimension_results["versatility"][0].score,
            utilization_score=dimension_results["utilization"][0].score,
            completeness_score=dimension_results["completeness"][0].score,
            balance_score=dimension_results["balance"][0].score,
            diversity_score=dimension_results["diversity"][0].score,
            confidence=total_confidence,
            explanations=explanations,
            items_count=ctx.items_count,
            outfits_count=ctx.outfits_count,
            wear_logs_count=ctx.wear_logs_count,
            diversity_config_snapshot=diversity_config,
        )

        # Generate suggestions
        suggestions = self.suggestion_generator.generate(ctx, dimension_results)
        suggestion_records = []

        if persist:
            session.add(score_record)
            await session.flush()  # Get score_record.id

            for sug in suggestions:
                record = WardrobeQualitySuggestion(
                    user_id=user_id,
                    score_id=score_record.id,
                    suggestion_type=sug.suggestion_type,
                    dimension=sug.dimension,
                    priority=sug.priority,
                    title=sug.title,
                    description=sug.description,
                    why=sug.why,
                    confidence=sug.confidence,
                    expected_impact=sug.expected_impact,
                    related_item_ids=sug.related_item_ids,
                )
                session.add(record)
                suggestion_records.append(record)

            await session.commit()
            await session.refresh(score_record)

        return score_record, suggestion_records

    async def get_latest_score(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> Optional[WardrobeQualityScore]:
        """Get the most recent quality score for a user."""
        result = await session.execute(
            select(WardrobeQualityScore)
            .where(WardrobeQualityScore.user_id == user_id)
            .order_by(WardrobeQualityScore.computed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_score_history(
        self,
        session: AsyncSession,
        user_id: str,
        limit: int = 10,
    ) -> List[WardrobeQualityScore]:
        """Get historical quality scores for a user."""
        result = await session.execute(
            select(WardrobeQualityScore)
            .where(WardrobeQualityScore.user_id == user_id)
            .order_by(WardrobeQualityScore.computed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cleanup_old_scores(
        self,
        session: AsyncSession,
        user_id: str,
        retention_days: int,
    ) -> int:
        """Delete scores older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await session.execute(
            delete(WardrobeQualityScore)
            .where(
                WardrobeQualityScore.user_id == user_id,
                WardrobeQualityScore.computed_at < cutoff,
            )
        )
        await session.commit()
        return result.rowcount

    async def _load_context(
        self,
        session: AsyncSession,
        user_id: str,
        diversity_config: dict,
    ) -> ScoringContext:
        """Load all wardrobe data needed for scoring."""
        # Load items
        items_result = await session.execute(
            select(Item).where(Item.user_id == user_id, Item.status == "active")
        )
        items = list(items_result.scalars().all())

        # Load outfits with their items
        outfits_result = await session.execute(
            select(Outfit)
            .where(Outfit.user_id == user_id)
            .options(selectinload(Outfit.items))
        )
        outfits = list(outfits_result.scalars().all())

        # Load outfit wear logs
        wear_logs_result = await session.execute(
            select(OutfitWearLog).where(
                OutfitWearLog.user_id == user_id,
                OutfitWearLog.deleted_at.is_(None),
            )
        )
        wear_logs = list(wear_logs_result.scalars().all())
        wear_log_ids = [log.id for log in wear_logs]

        # Load outfit wear log items (items worn via outfit logs)
        outfit_wear_log_items = []
        if wear_log_ids:
            owli_result = await session.execute(
                select(OutfitWearLogItem).where(
                    OutfitWearLogItem.wear_log_id.in_(wear_log_ids)
                )
            )
            outfit_wear_log_items = list(owli_result.scalars().all())

        # Load item wear logs
        item_wear_logs_result = await session.execute(
            select(ItemWearLog).where(
                ItemWearLog.user_id == user_id,
                ItemWearLog.deleted_at.is_(None),
            )
        )
        item_wear_logs = list(item_wear_logs_result.scalars().all())

        return ScoringContext(
            user_id=user_id,
            items=items,
            outfits=outfits,
            wear_logs=wear_logs,
            item_wear_logs=item_wear_logs,
            outfit_wear_log_items=outfit_wear_log_items,
            diversity_config=diversity_config,
        )
