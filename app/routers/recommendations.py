from fastapi import APIRouter, Depends
from app.schemas.recs import RecsOut
from app.services.recs import RecommendationService

router = APIRouter(tags=["recommendations"])


def get_recs_service() -> RecommendationService:
    return RecommendationService()


@router.get("/recommendations/items", response_model=RecsOut)
async def recommend_items(service: RecommendationService = Depends(get_recs_service)):
    return RecsOut(items=service.recommend_items("me"))


@router.get("/recommendations/outfits", response_model=RecsOut)
async def recommend_outfits(service: RecommendationService = Depends(get_recs_service)):
    return RecsOut(items=service.recommend_outfits("me"))
