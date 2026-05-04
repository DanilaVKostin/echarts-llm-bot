from fastapi import APIRouter, Query

from app.services.indicator_search import indicator_search_service

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search-indicators")
async def search_indicators(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50, description="Number of results"),
) -> list[dict]:
    return await indicator_search_service.search(q, top_k)


@router.get("/search-indicators/status")
async def indicator_search_status() -> dict:
    return await indicator_search_service.get_status()
