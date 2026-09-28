from fastapi import APIRouter
from src.services import agency as svc

router = APIRouter()


@router.get("/agencies")
async def search_agencies(active_only: bool = True):
    return await svc.list_agencies(active_only)
