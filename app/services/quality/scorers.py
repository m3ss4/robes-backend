from abc import ABC, abstractmethod
from typing import Dict, Set
from collections import Counter
from datetime import datetime, timedelta, timezone

from .types import DimensionResult, ScoringContext


class BaseScorer(ABC):
    """Base class for dimension scorers."""

    @property
    @abstractmethod
    def dimension_name(self) -> str:
        pass

    @abstractmethod
    def score(self, ctx: ScoringContext) -> DimensionResult:
        pass

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(100.0, value))


class VersatilityScorer(BaseScorer):
    """
    Versatility (30% weight): How many unique outfits can be created from items.

    Measures:
    - Item reuse across outfits (items appearing in multiple outfits)
    - Slot flexibility (items that work in multiple contexts)
    - Cross-category pairing potential
    """

    dimension_name = "versatility"

    def score(self, ctx: ScoringContext) -> DimensionResult:
        if ctx.items_count < 5:
            return DimensionResult(
                score=0.0,
                confidence=0.3,
                why="Need at least 5 items to assess versatility",
                contributing_factors=["insufficient_items"]
            )

        # Count how many outfits each item appears in
        item_outfit_count: Counter = Counter()
        for outfit in ctx.outfits:
            for oi in outfit.items:
                item_outfit_count[str(oi.item_id)] += 1

        if not item_outfit_count:
            return DimensionResult(
                score=30.0,
                confidence=0.5,
                why="No outfits created yet. Create outfits to see item versatility.",
                contributing_factors=["no_outfits"]
            )

        # Calculate metrics
        items_in_outfits = len(item_outfit_count)
        avg_outfits_per_item = sum(item_outfit_count.values()) / max(items_in_outfits, 1)
        items_in_multiple = sum(1 for c in item_outfit_count.values() if c > 1)
        reuse_ratio = items_in_multiple / max(items_in_outfits, 1)

        # Score calculation
        # - Base: items used in outfits / total items (0-40 points)
        # - Reuse bonus: items in 2+ outfits (0-40 points)
        # - Outfit density bonus (0-20 points)
        usage_ratio = items_in_outfits / ctx.items_count
        base_score = usage_ratio * 40
        reuse_score = reuse_ratio * 40
        density_score = min(avg_outfits_per_item / 3, 1.0) * 20

        total = self._clamp_score(base_score + reuse_score + density_score)

        factors = []
        if reuse_ratio > 0.5:
            factors.append("high_reuse")
        if usage_ratio < 0.3:
            factors.append("many_unused_items")

        why = f"{items_in_multiple} of {items_in_outfits} items appear in multiple outfits. "
        why += f"Average {avg_outfits_per_item:.1f} outfits per item."

        return DimensionResult(
            score=total,
            confidence=min(0.9, 0.5 + (ctx.outfits_count / 20)),
            why=why,
            contributing_factors=factors
        )


class UtilizationScorer(BaseScorer):
    """
    Utilization (25% weight): How actively items are being worn.

    Measures:
    - Wear frequency (items worn recently)
    - Neglected items (not worn in 30+ days)
    - Wear distribution (are some items over-worn vs never worn)
    """

    dimension_name = "utilization"

    def score(self, ctx: ScoringContext) -> DimensionResult:
        if ctx.items_count < 3:
            return DimensionResult(
                score=0.0,
                confidence=0.2,
                why="Need at least 3 items to assess utilization",
                contributing_factors=["insufficient_items"]
            )

        # Build wear counts per item
        item_wear_count: Counter = Counter()
        item_last_worn: Dict[str, datetime] = {}
        now = datetime.now(timezone.utc)

        # Build lookup from wear_log_id to worn_at timestamp
        # Defensive: fallback to created_at if worn_at is None
        wear_log_timestamps: Dict[str, datetime] = {
            str(log.id): (log.worn_at or log.created_at) for log in ctx.wear_logs
        }

        # Count items worn via outfit wear logs
        for owli in ctx.outfit_wear_log_items:
            item_id = str(owli.item_id)
            item_wear_count[item_id] += 1
            worn_at = wear_log_timestamps.get(str(owli.wear_log_id))
            if worn_at and (item_id not in item_last_worn or worn_at > item_last_worn[item_id]):
                item_last_worn[item_id] = worn_at

        for log in ctx.item_wear_logs:
            # Skip if this item wear came from an outfit log (already counted above)
            if getattr(log, 'source_outfit_log_id', None) is not None:
                continue
            item_id = str(log.item_id)
            item_wear_count[item_id] += 1
            # Defensive: fallback to created_at if worn_at is None
            worn_at = log.worn_at or log.created_at
            if worn_at and (item_id not in item_last_worn or worn_at > item_last_worn[item_id]):
                item_last_worn[item_id] = worn_at

        total_wears = sum(item_wear_count.values())
        items_worn = len(item_wear_count)
        items_never_worn = ctx.items_count - items_worn

        # Items not worn in 30+ days
        thirty_days_ago = now - timedelta(days=30)
        neglected = sum(
            1 for item_id, last in item_last_worn.items()
            if last < thirty_days_ago
        )

        if total_wears == 0:
            return DimensionResult(
                score=20.0,
                confidence=0.4,
                why="No wear logs recorded yet. Start logging what you wear!",
                contributing_factors=["no_wear_logs"]
            )

        # Score components
        # - Worn ratio: items worn at least once (0-35 points)
        # - Active ratio: items worn in last 30 days (0-35 points)
        # - Distribution: even wear distribution (0-30 points)
        worn_ratio = items_worn / ctx.items_count
        active_items = items_worn - neglected
        active_ratio = active_items / ctx.items_count if ctx.items_count > 0 else 0

        # Gini coefficient for wear distribution (0 = perfectly even, 1 = all one item)
        if items_worn > 1:
            sorted_counts = sorted(item_wear_count.values())
            n = len(sorted_counts)
            cumulative = sum((i + 1) * c for i, c in enumerate(sorted_counts))
            gini = (2 * cumulative) / (n * sum(sorted_counts)) - (n + 1) / n
            distribution_score = (1 - gini) * 30
        else:
            distribution_score = 15

        worn_score = worn_ratio * 35
        active_score = active_ratio * 35
        total = self._clamp_score(worn_score + active_score + distribution_score)

        factors = []
        if items_never_worn > ctx.items_count * 0.3:
            factors.append("many_unworn_items")
        if neglected > items_worn * 0.5:
            factors.append("many_neglected_items")

        why = f"{items_worn} of {ctx.items_count} items worn. "
        why += f"{items_never_worn} never worn, {neglected} neglected (30+ days)."

        return DimensionResult(
            score=total,
            confidence=min(0.95, 0.4 + (total_wears / 50)),
            why=why,
            contributing_factors=factors
        )


class CompletenessScorer(BaseScorer):
    """
    Completeness (20% weight): Essential wardrobe categories coverage.

    Measures:
    - Core categories present (tops, bottoms, footwear, outerwear)
    - Variety within categories (not just 1 of each)
    - Event coverage (casual, office, formal)
    """

    dimension_name = "completeness"

    CORE_CATEGORIES = {"top", "bottom", "footwear", "outerwear"}
    IMPORTANT_CATEGORIES = {"accessory", "onepiece"}

    def score(self, ctx: ScoringContext) -> DimensionResult:
        if ctx.items_count == 0:
            return DimensionResult(
                score=0.0,
                confidence=0.5,
                why="No items in wardrobe yet",
                contributing_factors=["empty_wardrobe"]
            )

        # Count items per category
        category_counts: Counter = Counter()
        event_coverage: Set[str] = set()

        for item in ctx.items:
            cat = item.category or item.kind
            category_counts[cat] += 1
            for tag in (item.event_tags or []):
                event_coverage.add(tag.lower())

        # Onepiece (dress/jumpsuit) counts as both top AND bottom for completeness
        onepiece_count = category_counts.get("onepiece", 0)
        effective_counts = dict(category_counts)
        if onepiece_count > 0:
            effective_counts["top"] = effective_counts.get("top", 0) + onepiece_count
            effective_counts["bottom"] = effective_counts.get("bottom", 0) + onepiece_count

        # Core categories present (using effective counts)
        core_present = sum(1 for c in self.CORE_CATEGORIES if effective_counts.get(c, 0) > 0)
        core_ratio = core_present / len(self.CORE_CATEGORIES)

        # Variety within categories (using effective counts)
        variety_score = sum(
            min(effective_counts.get(c, 0) / 3, 1.0)
            for c in self.CORE_CATEGORIES
        ) / len(self.CORE_CATEGORIES)

        # Event coverage
        event_score = min(len(event_coverage) / 4, 1.0)  # Target: 4 different events

        # Score components
        # - Core categories present (0-50 points)
        # - Variety within categories (0-30 points)
        # - Event coverage (0-20 points)
        total = self._clamp_score(
            core_ratio * 50 + variety_score * 30 + event_score * 20
        )

        factors = []
        missing = [c for c in self.CORE_CATEGORIES if effective_counts.get(c, 0) == 0]
        if missing:
            factors.append(f"missing_{missing[0]}")

        why = f"{core_present}/{len(self.CORE_CATEGORIES)} core categories covered"
        if onepiece_count > 0:
            why += f" (including {onepiece_count} onepiece)"
        why += ". "
        if missing:
            why += f"Missing: {', '.join(missing)}. "
        why += f"Event types: {len(event_coverage)}."

        return DimensionResult(
            score=total,
            confidence=0.9,  # High confidence - straightforward calculation
            why=why,
            contributing_factors=factors
        )


class BalanceScorer(BaseScorer):
    """
    Balance (15% weight): Proportions between categories.

    Measures:
    - Tops to bottoms ratio (ideal ~1:1 to 2:1)
    - Outerwear proportion
    - Accessories proportion
    """

    dimension_name = "balance"

    def score(self, ctx: ScoringContext) -> DimensionResult:
        if ctx.items_count < 5:
            return DimensionResult(
                score=50.0,
                confidence=0.3,
                why="Need more items to assess balance",
                contributing_factors=["insufficient_items"]
            )

        # Count by category
        category_counts: Counter = Counter()
        for item in ctx.items:
            cat = item.category or item.kind
            category_counts[cat] += 1

        # Onepiece counts as both top AND bottom for balance calculation
        onepiece_count = category_counts.get("onepiece", 0)
        tops = category_counts.get("top", 0) + onepiece_count
        bottoms = category_counts.get("bottom", 0) + onepiece_count
        outerwear = category_counts.get("outerwear", 0)
        footwear = category_counts.get("footwear", 0)

        # Tops to bottoms ratio (ideal: 1.0 to 2.0)
        if bottoms > 0:
            tb_ratio = tops / bottoms
            if 1.0 <= tb_ratio <= 2.0:
                tb_score = 40
            elif 0.5 <= tb_ratio <= 3.0:
                tb_score = 25
            else:
                tb_score = 10
        else:
            tb_score = 5 if tops > 0 else 0

        # Outerwear proportion (ideal: 10-20% of wardrobe)
        ow_ratio = outerwear / ctx.items_count if ctx.items_count > 0 else 0
        if 0.1 <= ow_ratio <= 0.25:
            ow_score = 30
        elif 0.05 <= ow_ratio <= 0.35:
            ow_score = 20
        elif outerwear > 0:
            ow_score = 10
        else:
            ow_score = 5

        # Footwear proportion (ideal: 10-15%)
        fw_ratio = footwear / ctx.items_count if ctx.items_count > 0 else 0
        if 0.08 <= fw_ratio <= 0.2:
            fw_score = 30
        elif footwear > 0:
            fw_score = 15
        else:
            fw_score = 5

        total = self._clamp_score(tb_score + ow_score + fw_score)

        factors = []
        if bottoms > 0 and (tops / bottoms > 3 or tops / bottoms < 0.5):
            factors.append("imbalanced_tops_bottoms")

        why = f"Tops:Bottoms ratio is {tops}:{bottoms}"
        if onepiece_count > 0:
            why += f" (including {onepiece_count} onepiece)"
        why += ". "
        why += f"Outerwear {outerwear} items ({ow_ratio*100:.0f}%), "
        why += f"Footwear {footwear} items ({fw_ratio*100:.0f}%)."

        return DimensionResult(
            score=total,
            confidence=0.85,
            why=why,
            contributing_factors=factors
        )


class DiversityScorer(BaseScorer):
    """
    Diversity (10% weight): Variety in selected attributes.

    Configurable per-user which attributes to include:
    - Colors (OFF by default)
    - Patterns (ON by default)
    - Seasons (ON by default)
    - Styles (ON by default)
    """

    dimension_name = "diversity"

    def score(self, ctx: ScoringContext) -> DimensionResult:
        if ctx.items_count < 3:
            return DimensionResult(
                score=50.0,
                confidence=0.3,
                why="Need more items to assess diversity",
                contributing_factors=["insufficient_items"]
            )

        config = ctx.diversity_config
        enabled_attrs = [k for k, v in config.items() if v]

        if not enabled_attrs:
            return DimensionResult(
                score=50.0,
                confidence=0.8,
                why="No diversity attributes enabled in preferences",
                contributing_factors=["no_attributes_enabled"]
            )

        scores = []
        factors = []

        # Colors diversity
        if config.get("colors", False):
            colors = [item.base_color for item in ctx.items if item.base_color]
            if colors:
                unique_colors = len(set(colors))
                color_score = min(unique_colors / 8, 1.0) * 100  # Target: 8+ colors
                scores.append(color_score)
                if unique_colors < 4:
                    factors.append("low_color_diversity")

        # Patterns diversity
        if config.get("patterns", True):
            patterns = [item.pattern for item in ctx.items if item.pattern]
            if patterns:
                unique_patterns = len(set(patterns))
                pattern_score = min(unique_patterns / 4, 1.0) * 100  # Target: 4+ patterns
                scores.append(pattern_score)

        # Seasons diversity
        if config.get("seasons", True):
            all_seasons: Set[str] = set()
            for item in ctx.items:
                for tag in (item.season_tags or []):
                    all_seasons.add(tag.lower())
            if all_seasons:
                season_score = min(len(all_seasons) / 4, 1.0) * 100  # Target: all 4 seasons
                scores.append(season_score)

        # Styles diversity
        if config.get("styles", True):
            all_styles: Set[str] = set()
            for item in ctx.items:
                for tag in (item.style_tags or []):
                    all_styles.add(tag.lower())
            if all_styles:
                style_score = min(len(all_styles) / 5, 1.0) * 100  # Target: 5+ styles
                scores.append(style_score)
                if len(all_styles) < 3:
                    factors.append("low_style_diversity")

        if not scores:
            return DimensionResult(
                score=50.0,
                confidence=0.4,
                why="Not enough attribute data to calculate diversity",
                contributing_factors=["missing_attribute_data"]
            )

        total = self._clamp_score(sum(scores) / len(scores))

        why = f"Diversity across {len(enabled_attrs)} enabled attributes. "
        why += f"Scored on: {', '.join(enabled_attrs)}."

        return DimensionResult(
            score=total,
            confidence=0.7,
            why=why,
            contributing_factors=factors
        )
