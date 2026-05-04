from fastapi import APIRouter

from app.services.rag import rag_service

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/status")
async def rag_status() -> dict:
    return await rag_service.check_status()
