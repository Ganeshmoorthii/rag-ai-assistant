from fastapi import APIRouter
from src.services import backorder as svc

router = APIRouter()


@router.get("/backorders")
async def search_backorders(status: str | None = None, agency_id: int | None = None):
    return await svc.list_backorders(status, agency_id)
