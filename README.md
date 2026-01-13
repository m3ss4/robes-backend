# Wardrobe OS — FastAPI backend (MVP)

FastAPI service + Celery worker for the Wardrobe OS MVP. Ships with:
- Async FastAPI API (`/v1`) + CORS for Expo
- Postgres (SQLAlchemy + Alembic migrations)
- Redis + Celery worker (image processing stub)
- Docker & docker-compose for one-command local dev

> Endpoints: `GET /v1/health`, `POST /v1/items`, `GET /v1/items`, `POST /v1/outfits/suggest`

---

## Quick start (Docker)

### 0) Prerequisites
- Docker Desktop (or Docker Engine) + Compose

### 1) Setup env
```bash
cp .env.example .env
```

### 2) Start stack
```bash
docker compose up --build
```

The API is at **http://localhost:8000**. Open docs at **/docs**.

### 3) Run DB migrations
In another terminal:
```bash
docker compose exec api alembic upgrade head
```

### 4) Test endpoints
```bash
curl http://localhost:8000/v1/health
curl -X POST http://localhost:8000/v1/items -H "Content-Type: application/json"   -d '{"kind":"top","name":"Navy tee","base_color":"navy","formality":0.2}'
curl -X POST http://localhost:8000/v1/outfits/suggest -H "Content-Type: application/json"   -d '{"mood":"calm","event":"office","timeOfDay":"morning"}'
```

### 5) Connect the Expo app
Start your Expo app with:
```bash
EXPO_PUBLIC_API_URL=http://localhost:8000 pnpm start
```
(Or add `extra.apiUrl` in its `app.json`).

---

## Local dev without Docker (optional)

### Python 3.11 venv
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Start worker (new shell):
```bash
celery -A workers.celery_app.celery worker -Q images -l info
```

## Project layout

```
app/
  main.py
  core/
    config.py     # settings via .env
    db.py         # async SQLAlchemy engine/session
  models/
    models.py     # Item, ItemImage
  routers/
    __init__.py
    health.py
    items.py
    outfits.py
  schemas/
    schemas.py    # Pydantic models
workers/
  celery_app.py
  tasks.py        # image processing stub
alembic/
  env.py
  versions/
    0001_init.py
requirements.txt
Dockerfile
docker-compose.yml
.env.example
```

## Notes & next steps

- The `/v1/outfits/suggest` endpoint returns **demo data** now; replace with your hybrid scoring.- Add pgvector later (and a migration) if you store embeddings.- For image uploads, add a `/v1/items/{id}/upload-url` route that returns presigned S3/R2 URLs. For local dev you can add MinIO to `docker-compose.yml`.- Lock down CORS in `.env` before sharing.- Add tests (pytest + httpx/pytest-asyncio) as you flesh out logic.

