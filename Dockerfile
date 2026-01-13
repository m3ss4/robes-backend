FROM python:3.11-slim AS weights
ARG CLIP_MODEL=ViT-B-32
ARG CLIP_PRETRAINED=laion2b_s34b_b79k

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates libgomp1 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install only what's needed to fetch weights once
RUN pip install --no-cache-dir torch==2.4.0 open-clip-torch==2.24.0

# Download the checkpoint via open-clip and copy to a stable path in /models
RUN python - <<'PY'
import open_clip, os, glob, shutil, pathlib

model = os.environ.get("CLIP_MODEL", "ViT-B-32")
pre   = os.environ.get("CLIP_PRETRAINED", "laion2b_s34b_b79k")
cache_dir = "/tmp/open_clip"

# triggers download into cache_dir
open_clip.create_model_and_transforms(model, pretrained=pre, cache_dir=cache_dir)

# open_clip-torch often stores weights as open_clip_pytorch_model.bin in a HF snapshot dir
cands = glob.glob(os.path.join(cache_dir, "**", "open_clip_pytorch_model.*"), recursive=True)

# fallback: anything that looks like a checkpoint
if not cands:
    patterns = ["*.safetensors", "*.pt", "*.pth", "*.bin", "*.npz"]
    for pat in patterns:
        cands.extend(glob.glob(os.path.join(cache_dir, "**", pat), recursive=True))

cands = [p for p in cands if os.path.isfile(p)]
cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)

print("All candidates in cache:", cands)

if not cands:
    raise SystemExit(f"Checkpoint not found for {model}:{pre} in {cache_dir}")

src = cands[0]
ext = pathlib.Path(src).suffix or ".bin"
dest = f"/models/open_clip/{model}/{pre}{ext}"
pathlib.Path(dest).parent.mkdir(parents=True, exist_ok=True)

shutil.copy2(src, dest)
print("Copied checkpoint to:", dest)
PY

# Optional: write a checksum file for verification in the next stage
RUN python - <<'PY'
import hashlib, os, glob
model = os.environ.get("CLIP_MODEL", "ViT-B-32")
pre   = os.environ.get("CLIP_PRETRAINED", "laion2b_s34b_b79k")
base  = f"/models/open_clip/{model}/{pre}"
matches = glob.glob(base + ".*")
if not matches:
    raise SystemExit(f"No baked checkpoint found at {base}.*")
p = matches[0]
sha = hashlib.sha256(open(p,"rb").read()).hexdigest()
open(p + ".sha256", "w").write(sha + "\\n")
print("Wrote checksum:", p + ".sha256")
PY

########## Stage 2: app runtime with baked weights ##########
FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (psycopg, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Bring in the weights from the first stage
ARG CLIP_MODEL=ViT-B-32
ARG CLIP_PRETRAINED=laion2b_s34b_b79k
COPY --from=weights /models /models

# Verify the checkpoint exists (optional hardening)
RUN python - <<'PY'
import os, glob
model = os.environ.get("CLIP_MODEL", "ViT-B-32")
pre   = os.environ.get("CLIP_PRETRAINED", "laion2b_s34b_b79k")
matches = glob.glob(f"/models/open_clip/{model}/{pre}.*")
assert matches, "No checkpoint baked into image"
print("Found checkpoint:", matches[0])
PY

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# CLIP env for runtime
ENV CLIP_MODEL=${CLIP_MODEL} \
    CLIP_PRETRAINED=${CLIP_PRETRAINED} \
    CLIP_CHECKPOINT_PATH=/models/open_clip/${CLIP_MODEL}/${CLIP_PRETRAINED}.bin

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
