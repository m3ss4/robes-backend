from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Tuple

import torch
import open_clip
from PIL import Image

from app.core.config import settings


def _device() -> torch.device:
    return torch.device("cpu")


@lru_cache(maxsize=1)
def _load_model():
    ckpt = os.environ.get("CLIP_CHECKPOINT_PATH") or settings.CLIP_CHECKPOINT_PATH
    pretrained = ckpt if ckpt and os.path.exists(ckpt) else settings.CLIP_PRETRAINED
    model, _, preprocess = open_clip.create_model_and_transforms(settings.CLIP_MODEL, pretrained=pretrained)
    tokenizer = open_clip.get_tokenizer(settings.CLIP_MODEL)
    model.to(_device())
    model.eval()
    return model, preprocess, tokenizer


def _encode_text(model, tokenizer, prompts: List[str]) -> torch.Tensor:
    tokens = tokenizer(prompts).to(_device())
    with torch.no_grad():
        txt = model.encode_text(tokens)
    txt = txt / txt.norm(dim=-1, keepdim=True)
    return txt


def _encode_image(model, preprocess, img: Image.Image) -> torch.Tensor:
    with torch.no_grad():
        image = preprocess(img).unsqueeze(0).to(_device())
        emb = model.encode_image(image)
    emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb


_FAMILY_LABELS = ["top", "bottom", "onepiece", "outerwear", "footwear", "accessory", "underlayer"]
_FAMILY_PROMPTS = [f"a photo of a {_} garment" for _ in _FAMILY_LABELS]

_TYPE_PROMPTS: Dict[str, List[Tuple[str, str]]] = {
    "top": [
        ("tshirt", "a short sleeve t-shirt"),
        ("shirt", "a button up shirt"),
        ("blouse", "a blouse"),
        ("knit", "a knit sweater"),
        ("hoodie", "a hoodie"),
        ("sweatshirt", "a sweatshirt"),
        ("polo", "a polo shirt"),
        ("tank", "a tank top"),
    ],
    "bottom": [
        ("jeans", "a pair of jeans"),
        ("chinos", "chino pants"),
        ("trousers", "dress trousers"),
        ("shorts", "shorts"),
        ("skirt", "a skirt"),
    ],
    "onepiece": [
        ("dress", "a dress"),
        ("jumpsuit", "a jumpsuit"),
    ],
    "outerwear": [
        ("jacket", "a jacket"),
        ("coat", "a coat"),
        ("blazer", "a blazer"),
        ("raincoat", "a raincoat"),
        ("puffer", "a puffer jacket"),
        ("gilet", "a gilet vest"),
    ],
    "footwear": [
        ("sneakers", "sneakers"),
        ("boots", "boots"),
        ("loafers", "loafers"),
        ("heels", "heels"),
        ("sandals", "sandals"),
    ],
    "accessory": [
        ("bag", "a bag"),
        ("scarf", "a scarf"),
        ("belt", "a belt"),
        ("hat", "a hat"),
        ("gloves", "gloves"),
    ],
}

_PATTERN_MAP = {
    "solid": "solid",
    "stripe": "stripe",
    "plaid": "check",
    "polka dot": "polka-dot",
    "floral": "floral",
    "animal print": "graphic",
    "graphic": "graphic",
}
_PATTERN_PROMPTS = [
    ("solid", "a solid color garment"),
    ("stripe", "a striped garment"),
    ("plaid", "a plaid or check garment"),
    ("polka dot", "a polka dot garment"),
    ("floral", "a floral print garment"),
    ("animal print", "an animal print garment"),
    ("graphic", "a graphic print garment"),
]


def _softmax(logits: torch.Tensor) -> torch.Tensor:
    return torch.softmax(logits, dim=-1)


def classify_image(img: Image.Image, family_hint: str | None = None) -> Dict[str, object]:
    model, preprocess, tokenizer = _load_model()
    img_emb = _encode_image(model, preprocess, img)

    # Family
    fam_txt = _encode_text(model, tokenizer, _FAMILY_PROMPTS)
    fam_logits = (model.logit_scale.exp() * img_emb @ fam_txt.T).squeeze(0)
    fam_probs = _softmax(fam_logits).cpu().tolist()
    fam_idx = int(torch.tensor(fam_probs).argmax())
    fam_label = _FAMILY_LABELS[fam_idx]
    fam_p = fam_probs[fam_idx]

    family = family_hint or fam_label

    # Type
    type_prompts = _TYPE_PROMPTS.get(family, _TYPE_PROMPTS.get(fam_label, []))
    type_out = {"clip_type": None, "clip_type_p": 0.0, "clip_type_top3": []}
    if type_prompts:
        labels, prompts = zip(*type_prompts)
        type_txt = _encode_text(model, tokenizer, list(prompts))
        logits = (model.logit_scale.exp() * img_emb @ type_txt.T).squeeze(0)
        probs = _softmax(logits).cpu()
        topk = min(3, len(labels))
        vals, idxs = torch.topk(probs, topk)
        type_out["clip_type_top3"] = [(labels[i], float(vals[j])) for j, i in enumerate(idxs.tolist())]
        type_out["clip_type"] = labels[idxs[0].item()]
        type_out["clip_type_p"] = float(vals[0])

    # Pattern
    pat_labels, pat_prompts = zip(*_PATTERN_PROMPTS)
    pat_txt = _encode_text(model, tokenizer, list(pat_prompts))
    pat_logits = (model.logit_scale.exp() * img_emb @ pat_txt.T).squeeze(0)
    pat_probs = _softmax(pat_logits).cpu()
    topk = min(3, len(pat_labels))
    p_vals, p_idxs = torch.topk(pat_probs, topk)
    pat_raw = pat_labels[p_idxs[0].item()]
    pat_val = _PATTERN_MAP.get(pat_raw, pat_raw)
    pattern_top3 = [(pat_labels[i], float(p_vals[j])) for j, i in enumerate(p_idxs.tolist())]

    return {
        "clip_family": family,
        "clip_family_p": float(fam_p),
        "clip_type": type_out.get("clip_type"),
        "clip_type_p": type_out.get("clip_type_p"),
        "clip_type_top3": type_out.get("clip_type_top3"),
        "clip_pattern": pat_val,
        "clip_pattern_p": float(p_vals[0]),
        "clip_pattern_top3": pattern_top3,
    }
