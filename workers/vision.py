import colorsys
import io
import math
import urllib.request
from typing import Any, Dict, Optional
from PIL import Image, ImageFilter, ImageStat
from app.core.config import settings

BASE_COLOR_RANGES = [
    ("red", [(345, 360), (0, 15)]),
    ("orange", [(15, 45)]),
    ("yellow", [(45, 70)]),
    ("green", [(70, 170)]),
    ("teal", [(170, 190)]),
    ("blue", [(190, 235)]),
    ("navy", [(215, 250)]),
    ("purple", [(250, 285)]),
    ("pink", [(285, 325)]),
    ("burgundy", [(325, 345)]),
]


def _open_image(image_url: Optional[str], image_b64: Optional[str]) -> tuple[Optional[Image.Image], Optional[str]]:
    if not image_url and not image_b64:
        return None, "no_image_provided"
    try:
        if image_b64:
            import base64

            raw = base64.b64decode(image_b64)
            return Image.open(io.BytesIO(raw)).convert("RGB"), None
        if image_url:
            with urllib.request.urlopen(image_url, timeout=2) as resp:
                data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB"), None
    except Exception as e:
        return None, str(e)
    return None, "unreadable_image"


def _dominant_rgb(img: Image.Image) -> tuple[int, int, int]:
    """Compute mean color on a center crop to reduce background bias."""
    w, h = img.size
    crop_margin_w = int(w * 0.15)
    crop_margin_h = int(h * 0.15)
    left = crop_margin_w
    upper = crop_margin_h
    right = w - crop_margin_w
    lower = h - crop_margin_h
    cropped = img.crop((left, upper, right, lower))
    small = cropped.copy()
    small.thumbnail((80, 80))
    stat = ImageStat.Stat(small)
    r, g, b = stat.mean[:3]
    return int(r), int(g), int(b)


def _solid_dominance(img: Image.Image) -> float:
    """Approximate solidity via palette dominance on a center crop."""
    cropped = _center_crop(img)
    quant = cropped.convert("RGB").quantize(colors=5, method=Image.MEDIANCUT)
    hist = quant.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    max_bucket = max(hist)
    return max_bucket / total


def _center_crop(img: Image.Image) -> Image.Image:
    w, h = img.size
    crop_margin_w = int(w * 0.1)
    crop_margin_h = int(h * 0.1)
    left = crop_margin_w
    upper = crop_margin_h
    right = w - crop_margin_w
    lower = h - crop_margin_h
    return img.crop((left, upper, right, lower))


def _hue_from_rgb(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def _map_base_color(hue: float, sat: float, val: float) -> str:
    if sat < 0.15:
        if val < 0.18:
            return "black"
        if val < 0.35:
            return "charcoal"
        if val < 0.6:
            return "gray"
        if val < 0.8:
            return "beige"
        return "white"
    for name, ranges in BASE_COLOR_RANGES:
        for low, high in ranges:
            if low <= hue <= high or (low > high and (hue >= low or hue <= high)):
                return name
    return "gray"


def _tone_from_hue(hue: float, sat: float, val: float) -> str:
    if sat < 0.12 or val < 0.15:
        return "neutral"
    if hue >= 200 or hue <= 80:
        return "cool"
    if 80 < hue < 190:
        return "warm" if hue < 140 else "neutral"
    return "neutral"


def _pattern_heuristic(img: Image.Image) -> tuple[str, float]:
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    stdev = stat.stddev[0] if stat.stddev else 0
    if stdev < 8:
        return "solid", 0.9
    if stdev < 16:
        return "stripe", 0.6
    if stdev < 26:
        return "check", 0.55
    return "graphic", 0.5


def _edge_density(img: Image.Image) -> float:
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    mean_edge = stat.mean[0]
    return mean_edge / 255.0


def _stripe_plaid_scores(img: Image.Image) -> tuple[float, float]:
    """Estimate stripe/plaid by variance of row/col means on a downscaled grayscale."""
    g = img.convert("L").resize((64, 64))
    pix = list(g.getdata())
    rows = [pix[i * 64 : (i + 1) * 64] for i in range(64)]
    cols = [pix[i::64] for i in range(64)]
    row_means = [sum(r) / len(r) for r in rows]
    col_means = [sum(c) / len(c) for c in cols]

    def _norm_std(vals):
        if not vals:
            return 0.0
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        if mean == 0:
            return 0.0
        return (var**0.5) / mean

    row_score = _norm_std(row_means)
    col_score = _norm_std(col_means)
    stripe_score = max(row_score, col_score)
    plaid_score = min(row_score, col_score)
    return stripe_score, plaid_score


def _dot_score(img: Image.Image) -> float:
    """Cheap dot heuristic: high-frequency edge density normalized."""
    g = img.convert("L").resize((64, 64))
    edges = g.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    mean_edge = stat.mean[0] / 255.0
    return min(1.0, mean_edge * 1.5)


def _category_type_guess(aspect: float, base_color: str, pattern: str, edge_density: float) -> tuple[str, str]:
    if aspect < 0.95:
        cat = "bottom"
        if aspect < 0.8:
            typ = "skirt"
        else:
            typ = "jeans" if base_color in {"blue", "navy"} else "trousers"
    elif aspect > 1.15:
        cat = "bottom"
        typ = "jeans" if base_color in {"blue", "navy"} else "trousers"
    else:
        cat = "top"
        typ = "shirt" if edge_density < 0.15 else "tshirt"
    if pattern in {"graphic"} and cat == "top":
        typ = "tshirt"
    return cat, typ


def _formality_prior(cat: str, typ: str, pattern: str, base_color: str) -> float:
    score = 0.5
    if typ in {"shirt", "blouse"}:
        score += 0.2
    if pattern in {"graphic"}:
        score -= 0.2
    if base_color in {"black", "navy", "white", "gray"}:
        score += 0.05
    return max(0.0, min(1.0, round(score, 2)))


def _warmth_prior(cat: str, base_color: str) -> int:
    if cat in {"outerwear"}:
        return 2
    if base_color in {"black", "navy"}:
        return 1
    return 0


def extract_features(image_url: Optional[str], image_b64: Optional[str]) -> Dict[str, Any]:
    img, err = _open_image(image_url, image_b64)
    if not img:
        return {"ok": False, "reason": err or "unreadable_image"}

    # Downscale for efficiency
    max_side = settings.IMGPROC_ANALYSIS_MAX_SIDE
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))

    rgb = _dominant_rgb(img)
    hue, sat, val = _hue_from_rgb(rgb)
    base_color = _map_base_color(hue, sat, val)
    tone = _tone_from_hue(hue, sat, val)
    solid_dom = _solid_dominance(img)
    edge_density = _edge_density(img)
    stripe_score, plaid_score = _stripe_plaid_scores(img)
    dot_score = _dot_score(img)

    pattern, pattern_conf = _pattern_heuristic(img)
    pattern_source = "vision"
    # Heuristic pattern overrides
    if solid_dom >= settings.SOLID_DOMINANCE_THR and edge_density < settings.EDGE_DENSITY_THR:
        pattern, pattern_conf, pattern_source = "solid", solid_dom, "solid_heuristic"
    elif stripe_score >= settings.STRIPE_THR and stripe_score > plaid_score:
        pattern, pattern_conf, pattern_source = "stripe", stripe_score, "stripe_heuristic"
    elif plaid_score >= settings.PLAID_THR:
        pattern, pattern_conf, pattern_source = "plaid", plaid_score, "plaid_heuristic"
    elif dot_score >= settings.DOT_THR and edge_density >= settings.MIN_EDGES_FOR_PATTERN:
        pattern, pattern_conf, pattern_source = "polka_dot", dot_score, "dot_heuristic"

    max_geom = max(stripe_score, plaid_score, dot_score)
    if edge_density < settings.MIN_EDGES_FOR_PATTERN and max_geom < settings.PATTERN_MIN_SCORE:
        pattern, pattern_conf, pattern_source = "solid", max(solid_dom, 0.3), "low_texture_assume_solid"
    elif max_geom < settings.PATTERN_MIN_SCORE:
        pattern, pattern_conf, pattern_source = "solid", max(solid_dom, 0.25), "low_pattern_signal"

    aspect = img.width / img.height if img.height else 1
    edges = edge_density
    category_guess, type_guess = _category_type_guess(aspect, base_color, pattern, edges)
    formality = _formality_prior(category_guess, type_guess, pattern, base_color)
    warmth = _warmth_prior(category_guess, base_color)

    result = {
        "ok": True,
        "base_color": base_color,
        "tone": tone,
        "pattern": pattern,
        "pattern_confidence": pattern_conf,
        "aspect_ratio": round(aspect, 2),
        "edge_density": round(edges, 3),
        "solid_score": round(solid_dom, 3),
        "stripe_score": round(stripe_score, 3),
        "plaid_score": round(plaid_score, 3),
        "dot_score": round(dot_score, 3),
        "pattern_source": pattern_source,
        "category": category_guess,
        "type": type_guess,
        "formality": formality,
        "warmth": warmth,
        "reason": f"hue~{int(hue)} sat~{int(sat*100)} val~{int(val*100)} aspect~{aspect:.2f} edges~{edges:.3f} pattern_conf~{pattern_conf} solid~{solid_dom:.2f} stripe~{stripe_score:.2f} plaid~{plaid_score:.2f} dot~{dot_score:.2f}",
    }
    result["debug_dims"] = {"width": img.width, "height": img.height}
    return result
