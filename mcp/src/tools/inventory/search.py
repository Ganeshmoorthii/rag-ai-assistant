from fastapi import APIRouter
from src.services import inventory as svc

router = APIRouter()


@router.get("/inventory")
async def search_inventory(low_stock: bool = False):
    return await svc.list_items(low_stock)
