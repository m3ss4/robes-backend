import json
import os
from typing import Any, Optional

from redis.asyncio import Redis

_redis: Optional[Redis] = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    return _redis


async def cache_json_get(key: str) -> Optional[Any]:
    val = await get_redis().get(key)
    return json.loads(val) if val else None


async def cache_json_set(key: str, data: Any, ttl: int) -> None:
    await get_redis().set(key, json.dumps(data), ex=ttl)
