import base64
import io

import pytest
from PIL import Image

from workers.vision import extract_features


def _img_b64(color: tuple[int, int, int]) -> str:
    im = Image.new("RGB", (50, 50), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_blue_image_maps_to_cool_color():
    b64 = _img_b64((30, 60, 200))
    features = extract_features(None, b64)
    assert features["ok"] is True
    assert features["base_color"] in {"blue", "navy"}
    assert features["tone"] == "cool"


def test_red_image_maps_to_warm_color():
    b64 = _img_b64((220, 40, 40))
    features = extract_features(None, b64)
    assert features["ok"] is True
    assert features["base_color"] in {"red", "burgundy"}
    assert features["tone"] in {"warm", "neutral"}


def test_pattern_and_formality_prior():
    img = Image.new("RGB", (50, 50))
    for x in range(50):
        for y in range(50):
            img.putpixel((x, y), (0, 0, 0) if (x + y) % 2 == 0 else (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    features = extract_features(None, b64)
    assert features["pattern"] in {"check", "graphic"}
    assert 0.0 <= features["formality"] <= 1.0
