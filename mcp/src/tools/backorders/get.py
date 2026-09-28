from fastapi import APIRouter
from src.services import backorder as svc

router = APIRouter()


@router.get("/backorders/{backorder_id}")
async def get_backorder(backorder_id: int):
    return await svc.get_backorder(backorder_id)
