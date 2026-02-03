from typing import Dict, List, Tuple
from collections import Counter

from .types import DimensionResult, ScoringContext, SuggestionData


class SuggestionGenerator:
    """Generates actionable suggestions based on scoring results."""

    def generate(
        self,
        ctx: ScoringContext,
        dimension_results: Dict[str, Tuple[DimensionResult, float]],
    ) -> List[SuggestionData]:
        """Generate suggestions ordered by priority and expected impact."""
        suggestions = []

        # Sort dimensions by score (lowest first) to prioritize improvements
        sorted_dims = sorted(
            dimension_results.items(),
            key=lambda x: x[1][0].score
        )

        for dim_name, (result, weight) in sorted_dims:
            if result.score >= 80:
                continue  # No suggestions needed for high-scoring dimensions

            dim_suggestions = self._suggestions_for_dimension(
                dim_name, result, weight, ctx
            )
            suggestions.extend(dim_suggestions)

        # Sort by priority, then expected impact
        suggestions.sort(key=lambda s: (s.priority, -(s.expected_impact or 0)))

        return suggestions[:10]  # Return top 10 suggestions

    def _suggestions_for_dimension(
        self,
        dim_name: str,
        result: DimensionResult,
        weight: float,
        ctx: ScoringContext,
    ) -> List[SuggestionData]:
        """Generate suggestions for a specific dimension."""
        if dim_name == "versatility":
            return self._versatility_suggestions(result, weight, ctx)
        elif dim_name == "utilization":
            return self._utilization_suggestions(result, weight, ctx)
        elif dim_name == "completeness":
            return self._completeness_suggestions(result, weight, ctx)
        elif dim_name == "balance":
            return self._balance_suggestions(result, weight, ctx)
        elif dim_name == "diversity":
            return self._diversity_suggestions(result, weight, ctx)
        return []

    def _versatility_suggestions(
        self, result: DimensionResult, weight: float, ctx: ScoringContext
    ) -> List[SuggestionData]:
        suggestions = []

        if "no_outfits" in result.contributing_factors:
            suggestions.append(SuggestionData(
                suggestion_type="create_outfit",
                dimension="versatility",
                priority=1,
                title="Create your first outfit",
                description="Combine your items into outfits to track versatility.",
                why="Creating outfits helps you see which items work well together and identifies pieces that could be styled more ways.",
                confidence=0.95,
                expected_impact=weight * 20,
            ))

        if "many_unused_items" in result.contributing_factors:
            # Find items not in any outfit
            used_items = set()
            for outfit in ctx.outfits:
                for oi in outfit.items:
                    used_items.add(str(oi.item_id))
            unused = [str(item.id) for item in ctx.items if str(item.id) not in used_items]

            if unused:
                suggestions.append(SuggestionData(
                    suggestion_type="use_in_outfit",
                    dimension="versatility",
                    priority=2,
                    title=f"Style {len(unused)} unused items",
                    description="These items haven't been added to any outfit yet.",
                    why="Adding unused items to outfits increases your wardrobe's versatility score and helps you get more value from your clothes.",
                    confidence=0.9,
                    expected_impact=weight * 15,
                    related_item_ids=unused[:5],
                ))

        return suggestions

    def _utilization_suggestions(
        self, result: DimensionResult, weight: float, ctx: ScoringContext
    ) -> List[SuggestionData]:
        suggestions = []

        if "no_wear_logs" in result.contributing_factors:
            suggestions.append(SuggestionData(
                suggestion_type="log_wear",
                dimension="utilization",
                priority=1,
                title="Start logging what you wear",
                description="Track your outfits to see utilization patterns.",
                why="Wear logging reveals which items you actually use versus which sit unworn, helping you make better wardrobe decisions.",
                confidence=0.95,
                expected_impact=weight * 25,
            ))

        if "many_unworn_items" in result.contributing_factors:
            # Find items never worn
            worn_items = set()
            for owli in ctx.outfit_wear_log_items:
                worn_items.add(str(owli.item_id))
            for log in ctx.item_wear_logs:
                # Skip if from outfit log (already counted above)
                if getattr(log, 'source_outfit_log_id', None) is not None:
                    continue
                worn_items.add(str(log.item_id))

            never_worn = [
                str(item.id) for item in ctx.items
                if str(item.id) not in worn_items
            ]

            if never_worn:
                suggestions.append(SuggestionData(
                    suggestion_type="wear_more",
                    dimension="utilization",
                    priority=2,
                    title=f"Wear {len(never_worn)} neglected items",
                    description="These items have never been logged as worn.",
                    why="Regularly wearing all your items improves utilization. Consider whether items you never wear should be donated or styled differently.",
                    confidence=0.85,
                    expected_impact=weight * 15,
                    related_item_ids=never_worn[:5],
                ))

        return suggestions

    def _completeness_suggestions(
        self, result: DimensionResult, weight: float, ctx: ScoringContext
    ) -> List[SuggestionData]:
        suggestions = []

        for factor in result.contributing_factors:
            if factor.startswith("missing_"):
                category = factor.replace("missing_", "")
                suggestions.append(SuggestionData(
                    suggestion_type="add_item",
                    dimension="completeness",
                    priority=1,
                    title=f"Add {category} to your wardrobe",
                    description=f"You're missing items in the {category} category.",
                    why=f"A complete wardrobe needs {category}. Adding this category will improve outfit options and completeness score.",
                    confidence=0.95,
                    expected_impact=weight * 12,
                ))

        if "empty_wardrobe" in result.contributing_factors:
            suggestions.append(SuggestionData(
                suggestion_type="add_item",
                dimension="completeness",
                priority=1,
                title="Add items to your wardrobe",
                description="Start by adding your essential clothing items.",
                why="Building a wardrobe starts with the basics. Add tops, bottoms, and footwear to begin tracking your style.",
                confidence=0.95,
                expected_impact=weight * 25,
            ))

        return suggestions

    def _balance_suggestions(
        self, result: DimensionResult, weight: float, ctx: ScoringContext
    ) -> List[SuggestionData]:
        suggestions = []

        if "imbalanced_tops_bottoms" in result.contributing_factors:
            category_counts = Counter()
            for item in ctx.items:
                cat = item.category or item.kind
                category_counts[cat] += 1

            # Onepiece counts as both top AND bottom
            onepiece_count = category_counts.get("onepiece", 0)
            tops = category_counts.get("top", 0) + onepiece_count
            bottoms = category_counts.get("bottom", 0) + onepiece_count

            if tops > bottoms * 2:
                suggestions.append(SuggestionData(
                    suggestion_type="add_item",
                    dimension="balance",
                    priority=2,
                    title="Add more bottoms",
                    description=f"You have {tops} tops but only {bottoms} bottoms.",
                    why="A balanced wardrobe has roughly 1-2 tops per bottom. Adding bottoms will create more outfit combinations.",
                    confidence=0.9,
                    expected_impact=weight * 10,
                ))
            elif bottoms > tops * 2:
                suggestions.append(SuggestionData(
                    suggestion_type="add_item",
                    dimension="balance",
                    priority=2,
                    title="Add more tops",
                    description=f"You have {bottoms} bottoms but only {tops} tops.",
                    why="You need more tops to pair with your bottoms. Consider versatile pieces that match multiple bottoms.",
                    confidence=0.9,
                    expected_impact=weight * 10,
                ))

        return suggestions

    def _diversity_suggestions(
        self, result: DimensionResult, weight: float, ctx: ScoringContext
    ) -> List[SuggestionData]:
        suggestions = []

        if "low_color_diversity" in result.contributing_factors:
            suggestions.append(SuggestionData(
                suggestion_type="add_item",
                dimension="diversity",
                priority=3,
                title="Add more color variety",
                description="Your wardrobe has limited color diversity.",
                why="A diverse color palette enables more outfit combinations and helps you dress for different moods and occasions.",
                confidence=0.8,
                expected_impact=weight * 8,
            ))

        if "low_style_diversity" in result.contributing_factors:
            suggestions.append(SuggestionData(
                suggestion_type="add_item",
                dimension="diversity",
                priority=3,
                title="Explore different styles",
                description="Your wardrobe style variety is limited.",
                why="Different style items help you adapt to various occasions from casual to formal settings.",
                confidence=0.8,
                expected_impact=weight * 8,
            ))

        return suggestions
