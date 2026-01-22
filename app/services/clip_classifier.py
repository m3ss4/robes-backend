from __future__ import annotations

import os
import logging
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
        ("cami_top", "a camisole top"),
        ("crop_top", "a crop top"),
        ("tunic_top", "a tunic top"),
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
        ("maxi_dress", "a maxi dress"),
        ("halter_dress", "a halter dress"),
        ("sleeveless_dress", "a sleeveless dress"),
        ("sundress", "a sundress"),
        ("shift_dress", "a shift dress"),
        ("tunic_dress", "a tunic dress"),
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

_TYPE_CANONICAL_MAP = {
    "halter_dress": "dress",
    "maxi_dress": "dress",
    "sleeveless_dress": "dress",
    "sundress": "dress",
    "shift_dress": "dress",
    "tunic_dress": "dress",
    "tunic_top": "tank",
    "cami_top": "tank",
    "crop_top": "tank",
}

_PATTERN_MAP = {
    "solid": "solid",
    "stripe": "stripe",
    "plaid": "check",
    "polka dot": "polka-dot",
    "floral": "floral",
    "animal print": "graphic",
    "graphic": "graphic",
    "text": "graphic",
}
_PATTERN_PROMPTS = [
    ("solid", "a solid color garment"),
    ("stripe", "a striped garment"),
    ("plaid", "a plaid or check garment"),
    ("polka dot", "a polka dot garment"),
    ("floral", "a floral print garment"),
    ("animal print", "an animal print garment"),
    ("graphic", "a graphic print garment"),
    ("text", "a garment with text or logo"),
]


def _softmax(logits: torch.Tensor) -> torch.Tensor:
    return torch.softmax(logits, dim=-1)


def _clip_type_probs(
    img_emb: torch.Tensor, model, tokenizer, labels: list[str], prompts: list[str]
) -> list[tuple[str, float]]:
    type_txt = _encode_text(model, tokenizer, list(prompts))
    logits = (model.logit_scale.exp() * img_emb @ type_txt.T).squeeze(0)
    probs = _softmax(logits).cpu()
    return [(labels[i], float(probs[i])) for i in range(len(labels))]


def classify_image(img: Image.Image, family_hint: str | None = None) -> Dict[str, object]:
    logger = logging.getLogger("clip_classifier")
    debug = os.getenv("DEBUG_CLIP", "").lower() in {"1", "true", "yes", "on"}
    model, preprocess, tokenizer = _load_model()
    img_emb = _encode_image(model, preprocess, img)

    # Family
    fam_txt = _encode_text(model, tokenizer, _FAMILY_PROMPTS)
    fam_logits = (model.logit_scale.exp() * img_emb @ fam_txt.T).squeeze(0)
    fam_probs = _softmax(fam_logits).cpu().tolist()
    fam_idx = int(torch.tensor(fam_probs).argmax())
    fam_label = _FAMILY_LABELS[fam_idx]
    fam_p = fam_probs[fam_idx]
    ranked = sorted(enumerate(fam_probs), key=lambda x: x[1], reverse=True)
    top2_idx, top2_prob = ranked[1] if len(ranked) > 1 else (None, 0.0)
    top2_label = _FAMILY_LABELS[top2_idx] if top2_idx is not None else None
    fam_margin = fam_p - top2_prob

    family = family_hint or fam_label

    # Type
    type_prompts = _TYPE_PROMPTS.get(family, _TYPE_PROMPTS.get(fam_label, []))
    if family_hint is None and (fam_p < 0.80 or fam_margin < 0.15):
        type_prompts = (_TYPE_PROMPTS.get("bottom", []) + _TYPE_PROMPTS.get("onepiece", []))
    type_out = {"clip_type": None, "clip_type_p": 0.0, "clip_type_top3": []}
    if type_prompts:
        labels, prompts = zip(*type_prompts)
        probs = _clip_type_probs(img_emb, model, tokenizer, list(labels), list(prompts))
        probs_tensor = torch.tensor([p[1] for p in probs])
        topk = min(3, len(labels))
        vals, idxs = torch.topk(probs_tensor, topk)
        type_out["clip_type_top3"] = [(probs[i][0], float(vals[j])) for j, i in enumerate(idxs.tolist())]
        type_out["clip_type"] = probs[idxs[0].item()][0]
        type_out["clip_type_p"] = float(vals[0])
        if debug:
            logger.info(
                "clip:family=%s fam_p=%.3f margin=%.3f type_labels=%s top3=%s",
                fam_label,
                fam_p,
                fam_margin,
                list(labels),
                type_out["clip_type_top3"],
            )
        mapped_top3: Dict[str, float] = {}
        for label, score in type_out["clip_type_top3"]:
            canon = _TYPE_CANONICAL_MAP.get(label, label)
            mapped_top3[canon] = max(mapped_top3.get(canon, 0.0), float(score))
        type_out["clip_type_top3"] = sorted(mapped_top3.items(), key=lambda x: x[1], reverse=True)
        if type_out["clip_type"] in _TYPE_CANONICAL_MAP:
            type_out["clip_type"] = _TYPE_CANONICAL_MAP[type_out["clip_type"]]
        if type_out["clip_type"] == "skirt":
            top3_map = {label: score for label, score in type_out["clip_type_top3"]}
            skirt_p = top3_map.get("skirt")
            dress_p = top3_map.get("dress")
            if skirt_p is not None and dress_p is not None and (skirt_p - dress_p) < 0.10:
                aspect = (img.height / img.width) if img.width else 1.0
                if aspect >= 1.35:
                    type_out["clip_type"] = "dress"
                    type_out["clip_type_p"] = max(type_out["clip_type_p"], float(dress_p))
        if type_out["clip_type"] == "skirt":
            override_labels = [
                "skirt",
                "skirt",
                "dress",
                "dress",
                "dress",
                "dress",
                "jumpsuit",
            ]
            override_prompts = [
                "a skirt laid flat",
                "a long skirt laid flat",
                "a sleeveless dress laid flat",
                "a halter neck dress laid flat",
                "a maxi dress laid flat",
                "a long summer dress laid flat",
                "a jumpsuit laid flat",
            ]
            override_probs = _clip_type_probs(img_emb, model, tokenizer, override_labels, override_prompts)
            skirt_score = max(p for lbl, p in override_probs if lbl == "skirt")
            dress_score = max(p for lbl, p in override_probs if lbl == "dress")
            if dress_score >= (skirt_score - 0.05) and dress_score >= 0.30:
                type_out["clip_type"] = "dress"
                type_out["clip_type_p"] = max(type_out["clip_type_p"], float(dress_score))
                if debug:
                    logger.info(
                        "clip:skirt_vs_dress_override skirt=%.3f dress=%.3f top3=%s",
                        skirt_score,
                        dress_score,
                        override_probs,
                    )

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
    if pat_raw == "stripe":
        for label, score in pattern_top3:
            if label in {"graphic", "text"} and score >= (float(p_vals[0]) - 0.10):
                pat_val = _PATTERN_MAP.get(label, label)
                break

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
