"""
Synthetic fixtures for quality scoring edge cases.
Use these to create consistent test scenarios.
"""
from typing import Dict, Any


def empty_wardrobe_fixture() -> Dict[str, Any]:
    """Fixture representing empty wardrobe."""
    return {
        "items": [],
        "outfits": [],
        "wear_logs": [],
        "expected_scores": {
            "completeness": 0,
            "versatility": 0,
            "utilization": 0,
        }
    }


def minimal_wardrobe_fixture() -> Dict[str, Any]:
    """Fixture with minimum viable wardrobe (< 5 items)."""
    return {
        "items": [
            {"kind": "top", "name": "Basic Tee", "base_color": "white"},
            {"kind": "bottom", "name": "Jeans", "base_color": "blue"},
            {"kind": "footwear", "name": "Sneakers", "base_color": "white"},
        ],
        "outfits": [],
        "wear_logs": [],
        "expected_confidence": {"versatility": 0.3, "utilization": 0.2},
    }


def heavy_usage_fixture() -> Dict[str, Any]:
    """Fixture with heavily used wardrobe."""
    items = [
        {"kind": "top", "name": f"Top{i}", "base_color": "black"}
        for i in range(5)
    ]
    items.extend([
        {"kind": "bottom", "name": f"Bottom{i}", "base_color": "blue"}
        for i in range(3)
    ])
    items.append({"kind": "footwear", "name": "Boots", "base_color": "black"})

    # Outfits using most items
    outfits = [
        {"name": f"Outfit{i}", "items": [
            {"slot": "top", "item_index": i % 5},
            {"slot": "bottom", "item_index": 5 + (i % 3)},
            {"slot": "shoes", "item_index": 8},
        ]}
        for i in range(10)
    ]

    # Many wear logs
    wear_logs = [{"outfit_index": i % 10} for i in range(50)]

    return {
        "items": items,
        "outfits": outfits,
        "wear_logs": wear_logs,
        "expected_scores": {
            "utilization": {"min": 60},
            "versatility": {"min": 50},
        }
    }


def missing_categories_fixture() -> Dict[str, Any]:
    """Fixture with missing essential categories."""
    return {
        "items": [
            {"kind": "top", "name": f"Top{i}", "base_color": "white"}
            for i in range(8)
        ],  # Only tops, missing bottoms, footwear, outerwear
        "outfits": [],
        "wear_logs": [],
        "expected_scores": {
            "completeness": {"max": 30},
            "balance": {"max": 40},
        },
        "expected_suggestions": [
            {"type": "add_item", "dimension": "completeness"},
        ]
    }


def imbalanced_wardrobe_fixture() -> Dict[str, Any]:
    """Fixture with imbalanced category proportions."""
    items = [
        {"kind": "top", "name": f"Top{i}", "base_color": "black"}
        for i in range(15)  # Too many tops
    ]
    items.extend([
        {"kind": "bottom", "name": "Single Bottom", "base_color": "blue"},
        {"kind": "footwear", "name": "Single Shoes", "base_color": "black"},
    ])

    return {
        "items": items,
        "outfits": [],
        "wear_logs": [],
        "expected_scores": {
            "balance": {"max": 50},
        },
        "expected_suggestions": [
            {"type": "add_item", "dimension": "balance", "contains": "bottom"},
        ]
    }


def low_diversity_fixture() -> Dict[str, Any]:
    """Fixture with low attribute diversity."""
    items = [
        {"kind": "top", "name": f"Black Top{i}", "base_color": "black",
         "pattern": "solid", "style_tags": ["casual"], "season_tags": ["summer"]}
        for i in range(5)
    ]
    items.extend([
        {"kind": "bottom", "name": f"Black Bottom{i}", "base_color": "black",
         "pattern": "solid", "style_tags": ["casual"], "season_tags": ["summer"]}
        for i in range(3)
    ])

    return {
        "items": items,
        "outfits": [],
        "wear_logs": [],
        "diversity_config": {"colors": True, "patterns": True, "seasons": True, "styles": True},
        "expected_scores": {
            "diversity": {"max": 40},
        },
        "expected_suggestions": [
            {"type": "add_item", "dimension": "diversity", "contains": "color"},
        ]
    }


def well_balanced_fixture() -> Dict[str, Any]:
    """Fixture representing an optimal wardrobe."""
    items = []
    # Balanced tops and bottoms
    for i, color in enumerate(["white", "black", "blue", "gray", "navy"]):
        items.append({
            "kind": "top", "name": f"Top {color}",
            "base_color": color,
            "pattern": ["solid", "striped", "solid", "solid", "solid"][i],
            "style_tags": [["casual", "smart-casual"], ["office"]][i % 2],
            "season_tags": [["spring", "summer"], ["fall", "winter"], ["spring", "fall"]][i % 3],
        })

    for i, color in enumerate(["black", "blue", "khaki"]):
        items.append({
            "kind": "bottom", "name": f"Pants {color}",
            "base_color": color,
            "style_tags": [["casual"], ["office"]][i % 2],
            "season_tags": ["spring", "summer", "fall", "winter"],
        })

    # Footwear
    items.extend([
        {"kind": "footwear", "name": "Sneakers", "base_color": "white", "style_tags": ["casual"]},
        {"kind": "footwear", "name": "Dress Shoes", "base_color": "black", "style_tags": ["formal"]},
    ])

    # Outerwear
    items.append({
        "kind": "outerwear", "name": "Blazer",
        "base_color": "navy",
        "style_tags": ["smart-casual", "office"],
    })

    return {
        "items": items,
        "expected_scores": {
            "completeness": {"min": 80},
            "balance": {"min": 70},
            "diversity": {"min": 60},
        }
    }


ALL_FIXTURES = {
    "empty": empty_wardrobe_fixture,
    "minimal": minimal_wardrobe_fixture,
    "heavy_usage": heavy_usage_fixture,
    "missing_categories": missing_categories_fixture,
    "imbalanced": imbalanced_wardrobe_fixture,
    "low_diversity": low_diversity_fixture,
    "well_balanced": well_balanced_fixture,
}
