# Growth Modules Removal Checklist

Use this to remove the growth scaffolding (search, recommendations, notifications) cleanly.

## 1) Disable feature flags

In `.env` or runtime config, ensure these are false:

- SEARCH_ENABLED=false
- RECS_ENABLED=false
- NOTIFICATIONS_ENABLED=false

## 2) Remove optional router includes

Edit `app/main.py` and remove these imports and conditional includes:

- `from app.routers import search as search_router`
- `from app.routers import recommendations as recommendations_router`
- `from app.routers import notifications as notifications_router`

And remove the three `if settings.<...>_ENABLED:` blocks that include those routers.

## 3) Remove config flags

Edit `app/core/config.py` and remove:

- `SEARCH_ENABLED`
- `RECS_ENABLED`
- `NOTIFICATIONS_ENABLED`

## 4) Remove schema exports

Edit `app/schemas/schemas.py` and remove the imports and `__all__` entries for:

- search schemas (`SearchHitOut`, `SearchItemsOut`, `SearchOutfitsOut`)
- recs schemas (`RecOut`, `RecsOut`)
- notifications schemas (`NotificationOut`, `NotificationsOut`)

## 5) Delete module files

Delete these directories/files:

- `app/search/`
- `app/services/search/`
- `app/routers/search.py`
- `app/schemas/search.py`
- `docs/search.md`
- `tests/test_search_stub.py`
- `scripts/reindex_search.py`

- `app/recs/`
- `app/services/recs/`
- `app/routers/recommendations.py`
- `app/schemas/recs.py`
- `docs/recs.md`
- `tests/test_recs_stub.py`
- `scripts/rebuild_recs_cache.py`

- `app/notifications/`
- `app/services/notifications/`
- `app/routers/notifications.py`
- `app/schemas/notifications.py`
- `workers/notifications.py`
- `docs/notifications.md`
- `tests/test_notifications_stub.py`
- `scripts/preview_notifications.py`

## 6) Clean up any imports

Search for these module prefixes and remove any stray imports:

- `app.search`
- `app.recs`
- `app.notifications`
- `app.services.search`
- `app.services.recs`
- `app.services.notifications`

## 7) Optional: remove this checklist

Delete `docs/growth_removal_checklist.md` if you don’t need it anymore.
