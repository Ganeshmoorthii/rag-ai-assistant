from fastapi import APIRouter
from src.services import inventory as svc

router = APIRouter()


@router.get("/inventory/{sku}")
async def get_item(sku: str):
    return await svc.get_item(sku)
