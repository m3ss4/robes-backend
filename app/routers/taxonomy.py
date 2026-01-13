from fastapi import APIRouter
from app.core.taxonomy import get_taxonomy

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])

_cache = None

@router.get("")
async def read_taxonomy():
    global _cache
    if _cache is None:
        _cache = get_taxonomy()
    return _cache
