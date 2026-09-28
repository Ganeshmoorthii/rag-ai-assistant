from fastapi import APIRouter
from src.schemas.inventory.schema import InventoryItemCreate
from src.services import inventory as svc

router = APIRouter()


@router.post("/inventory", status_code=201)
async def create_item(body: InventoryItemCreate):
    return await svc.create_item(body)


@router.delete("/inventory/{sku}", status_code=204)
async def delete_item(sku: str):
    await svc.delete_item(sku)
