import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import health, items, outfits
from app.routers import tags as tags_router
from app.routers import taxonomy as taxonomy_router
from app.routers import auth as auth_router
from app.routers import sessions as sessions_router
from app.llm.base import ProviderRegistry
from app.llm.openai_provider import OpenAIProvider
from app.llm.local_provider import LocalProvider

app = FastAPI(title=settings.APP_NAME)

# CORS
origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.API_PREFIX
app.include_router(health.router, prefix=prefix)
app.include_router(items.router, prefix=prefix)
app.include_router(outfits.router, prefix=prefix)
app.include_router(tags_router.router, prefix=prefix)
app.include_router(taxonomy_router.router, prefix=prefix)
app.include_router(auth_router.router, prefix=prefix)
app.include_router(sessions_router.router, prefix=prefix)

# LLM providers
try:
    ProviderRegistry.register("local", LocalProvider())
    ProviderRegistry.register("openai", OpenAIProvider())
except Exception:
    # Fail soft; provider resolved later
    pass

logger = logging.getLogger("app.requests")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, duration_ms)
    return response

@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "env": settings.APP_ENV}
