# Wardrobe OS — AI Helper Context

You are assisting on a cross-platform wardrobe app.

## Goal

Ship a reliable MVP that answers **“What should I wear now?”** from the user’s real wardrobe, with:

- Context: **weather, event, time of day, mood**
- Clear **explanations** (“why this outfit”)
- Fast **inventory** capture and **packing** for trips

## Tech Stack

- **Mobile/Web:** Expo React Native (RN 0.74 / Expo SDK 51), TypeScript, Expo Router, TanStack Query, Zustand, NativeWind (Tailwind for RN).
- **Backend:** FastAPI (Python 3.11), Pydantic v2, SQLAlchemy 2 (async), Alembic, Postgres, Redis, Celery.
- **Infra (dev):** Docker Compose (api, worker, postgres, redis). API served at `http://localhost:8000`.

## Repos

- `wardrobe-os-expo/` (app) — already includes tabs: Suggest, Inventory, Pack.
- `wardrobe-os-fastapi/` (backend) — endpoints:
  - `GET /v1/health`
  - `POST /v1/items`
  - `GET /v1/items`
  - `POST /v1/outfits/suggest` (returns demo data; replace with scoring later)

## Product Constraints (MVP)

- **Must-have:** item upload + tagging, context capture, 3 outfit suggestions w/ rationale, wear log stub, packing (greedy capsule baseline).
- **Non-goals (for MVP):** social/sharing, shopping, heavy ML/vision, multi-tenant billing.
- **Guardrails:** Don’t suggest suede/non-waterproof in rain; respect user “avoid” materials; rotate under-worn items.

## Data Contracts (initial)

### Backend → App: Outfit Suggest (response)

```json
{
  "outfits": [
    {
      "id": "uuid-or-string",
      "score": 0.0,
      "rationale": ["string"],
      "slots": { "top": "item-id", "bottom": "item-id", "footwear": "item-id", "outerwear": "item-id", "accessories": ["item-id"] }
    }
  ]
}
```

### App → Backend: Outfit Suggest (request)
{
  "mood": "calm|bold|cozy",
  "event": "office|casual|evening|... (string)",
  "timeOfDay": "morning|afternoon|evening",
  "datetime": "ISO 8601 string",
  "location": null | { "lat": number, "lon": number }
}
```
```
### Items (simplified)
type Item = {
  id: string;
  kind: "top"|"bottom"|"onepiece"|"outerwear"|"footwear"|"accessory";
  name?: string;
  brand?: string;
  base_color?: string;
  material?: string;
  warmth?: -2|-1|0|1|2;
  formality?: number; // 0 casual → 1 formal
  style_tags?: string[];
  event_tags?: string[];
  season_tags?: string[];
};
```

## Coding Standards

### Backend (FastAPI)

Async everything. Dependency-injected DB session via app.core.db.get_session.

Pydantic v2 models in app/schemas. Keep response schemas separate from ORM models.

DB changes via Alembic migrations only.

Queue work via Celery tasks; no long-running work in request handlers.

CORS permissive in dev; tighten before sharing.

### Testable Acceptance Criteria (MVP)

From app launch to “Wear this”: ≤ 5s compute, ≤ 3 taps.

3 suggestions returned with rationale bullets.

Packing screen outputs a minimal list for a 3–7 day trip (greedy capsule baseline).

Health endpoint up; items can be created/listed; suggest returns well-formed JSON.

### Don’ts for AI

Don’t invent endpoints or DB columns not listed here.

Don’t add heavy ML/vision in MVP (use stubs + TODOs).

Don’t block UI on network; always show graceful placeholders.

### TODO (next tasks)

App: implement “Wear this” → call /v1/outfits/accept (backend stub first) and append to a local wear log.

App: Inventory → add presigned upload flow (backend endpoint stub first).

Backend: /v1/items/{id}/upload-url (S3/R2 or local MinIO later), /v1/outfits/accept, /v1/pack/generate (baseline).

Backend: add simple scoring for weather/formality/mood/rotation; keep color harmony rule-based.

Style Examples

React Query:
```
const { data, isLoading } = useQuery({
  queryKey: ["suggest", ctx],
  queryFn: () => suggestOutfits(ctx),
});
```

FastAPI route:
```
@router.post("/suggest", response_model=OutfitSuggestOut)
async def suggest_outfits(ctx: OutfitSuggestIn, session: AsyncSession = Depends(get_session)):
    # TODO: replace with real scoring; keep response format stable
    return OutfitSuggestOut(outfits=[...])
```


## docs/COPILOT_PROMPTS.md (optional helper for you to paste in chat)
## Prompt: implement outfit scoring (backend)
You are adding rule-based scoring to FastAPI endpoint `/v1/outfits/suggest`. Constraints:
- Keep request/response schemas in `app/schemas/schemas.py`.
- Use weather/formality/mood/rotation scalars and sum a score (0..1).
- No heavy ML; if needed add TODOs.
- Read only from in-memory demo inventory for now (array at top of file).
- Return 3 best with `"rationale"` explaining major score contributions.

Deliverables:
- Update `app/routers/outfits.py` with a pure-Python scoring function and rationale bullets.
- Add unit tests in `tests/test_outfits.py` (create the `tests` package if missing).
- Don’t change endpoint path or response schema.

## Prompt: add presigned upload flow
Goal: Add `POST /v1/items/{id}/upload-url` returning `{url, fields}` for S3-compatible multipart POST (R2/MinIO later).
- Don’t integrate real S3 now; return a fake URL and fields plus a TODO.
- Add Expo app call in `lib/api.ts` and a button in `app/(tabs)/inventory.tsx` to trigger it.
- Keep TypeScript strict; handle Android/Simulator URL differences.

## Prompt: wear log on accept
Add a “Wear this” handler in the app that POSTs to `/v1/outfits/accept` with `{outfitId, ctx}`.
- Create backend route returning `{ok:true}` and log to console (TODO persist later).
- Optimistically update UI.
- Add minimal unit test for the route.

## docs/CONTRIBUTING.md 
# Contributing

- Code style: TypeScript strict; Python black/isort/ruff (add later).
- Small PRs, each tied to an issue with acceptance criteria.
- Keep API contracts stable; update `AI_CONTEXT.md` if a contract changes.
- Add/adjust Alembic migrations for any DB change.
- For non-trivial logic, add a quick “why” in code comments.

