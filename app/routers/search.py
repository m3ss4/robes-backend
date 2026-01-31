from fastapi import APIRouter, Depends, Query
from app.schemas.search import SearchItemsOut, SearchOutfitsOut
from app.services.search import SearchService

router = APIRouter(tags=["search"])


def get_search_service() -> SearchService:
    return SearchService()


@router.get("/search/items", response_model=SearchItemsOut)
async def search_items(q: str = Query(""), limit: int = Query(20, ge=1, le=100), service: SearchService = Depends(get_search_service)):
    res = service.search_items(q, limit)
    return SearchItemsOut(took_ms=res.took_ms, hits=res.hits)


@router.get("/search/outfits", response_model=SearchOutfitsOut)
async def search_outfits(q: str = Query(""), limit: int = Query(20, ge=1, le=100), service: SearchService = Depends(get_search_service)):
    res = service.search_outfits(q, limit)
    return SearchOutfitsOut(took_ms=res.took_ms, hits=res.hits)
