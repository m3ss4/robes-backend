from __future__ import annotations

import os
from functools import lru_cache
from typing import List

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
    model.to(_device())
    model.eval()
    return model, preprocess


def embed_image(img: Image.Image) -> List[float]:
    model, preprocess = _load_model()
    with torch.no_grad():
        image = preprocess(img).unsqueeze(0).to(_device())
        emb = model.encode_image(image)
    emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.squeeze(0).cpu().tolist()
