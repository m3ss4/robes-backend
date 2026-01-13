import pytest

from app.core.tags import ALLOWED_SEASONS, clamp_limits, normalize_many, normalize_tag

def test_normalize_basic_slug():
    assert normalize_tag(" Boho/Chic ") == "boho-chic"
    assert normalize_tag("Street   Wear") == "street-wear"

def test_normalize_unicode_and_case():
    assert normalize_tag("Café Crème") == "cafe-creme"
    assert normalize_tag("Ästhetic") == "asthetic"

def test_normalize_many_dedupes():
    assert normalize_many(["Minimal", "minimal", "  minimal  "]) == ["minimal"]

def test_length_bounds():
    with pytest.raises(ValueError):
        normalize_tag("a" * 25)
    assert normalize_tag("a" * 24) == "a" * 24

def test_clamp_limits():
    styles, events, seasons = clamp_limits(
        ["s1"] * 12, ["e1", "e2", "e3", "e4", "e5", "e6", "e7"], ["spring", "winter", "monsoon"]
    )
    assert len(styles) == 10
    assert len(events) == 6
    assert seasons == ["spring", "winter"]
    for s in seasons:
        assert s in ALLOWED_SEASONS
