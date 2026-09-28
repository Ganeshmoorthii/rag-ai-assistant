from fastapi import APIRouter
from src.schemas.inventory.schema import RestockRequest
from src.services import inventory as svc

router = APIRouter()


@router.post("/inventory/{sku}/restock")
async def restock_item(sku: str, body: RestockRequest):
    """Maps directly to SDK v3 restockItem({ sku, quantity, requestedBy })."""
    return await svc.restock_item(sku, body)
