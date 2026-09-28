from src.repositories import inventory as repo
from src.schemas.inventory.schema import InventoryItemCreate, RestockRequest
from src.utils.errors import NotFoundError, ValidationError


async def list_items(low_stock: bool = False) -> list[dict]:
    return await repo.find_all(low_stock)


async def get_item(sku: str) -> dict:
    row = await repo.find_by_sku(sku)
    if not row:
        raise NotFoundError("Item", sku)
    return row


async def create_item(body: InventoryItemCreate) -> dict:
    return await repo.create(
        body.sku, body.item_name, body.unit_cost,
        body.quantity_on_hand, body.warehouse_location, body.reorder_threshold,
    )


async def restock_item(sku: str, body: RestockRequest) -> dict:
    """SDK v3 restockItem() — increments stock and logs the request."""
    if body.quantity <= 0:
        raise ValidationError("quantity must be greater than 0")
    item = await repo.find_by_sku(sku)
    if not item:
        raise NotFoundError("Item", sku)
    updated = await repo.add_quantity(sku, body.quantity)
    await repo.log_restock(item["id"], body.requested_by, body.quantity)
    return {"updated_item": updated, "restocked_qty": body.quantity}


async def delete_item(sku: str) -> None:
    row = await repo.find_by_sku(sku)
    if not row:
        raise NotFoundError("Item", sku)
    await repo.delete(sku)
