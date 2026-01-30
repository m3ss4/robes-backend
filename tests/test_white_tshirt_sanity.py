import os

import pytest
from PIL import Image

from app.services.clip_classifier import classify_image


ASSET_DIR = os.getenv("TEST_IMAGE_DIR", "tests/assets")


def _load(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


@pytest.mark.skipif(not os.path.isdir(ASSET_DIR), reason="missing test assets")
def test_white_tshirt_product_sanity():
    path = os.path.join(ASSET_DIR, "white_tshirt_product.jpg")
    if not os.path.exists(path):
        pytest.skip("missing white tshirt asset")
    out = classify_image(_load(path))
    assert out.get("clip_family") == "top"
    assert out.get("clip_type") in {"tshirt", "tank", "shirt"}
