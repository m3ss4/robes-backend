import os

import pytest
from PIL import Image

from app.services.clip_classifier import classify_image


ASSET_DIR = os.getenv("TEST_IMAGE_DIR", "tests/assets")


def _load(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


@pytest.mark.skipif(not os.path.isdir(ASSET_DIR), reason="missing test assets")
def test_skirt_vs_dress_sanity():
    dress_path = os.path.join(ASSET_DIR, "flatlay_maxi_dress.jpg")
    skirt_path = os.path.join(ASSET_DIR, "flatlay_skirt.jpg")
    if not (os.path.exists(dress_path) and os.path.exists(skirt_path)):
        pytest.skip("missing dress/skirt assets")

    dress = classify_image(_load(dress_path))
    skirt = classify_image(_load(skirt_path))

    assert dress.get("clip_type") == "dress"
    assert skirt.get("clip_type") == "skirt"
