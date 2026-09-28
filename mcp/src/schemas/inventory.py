from pydantic import BaseModel


class InventoryItemCreate(BaseModel):
    sku: str
    item_name: str | None = None
    unit_cost: float | None = None
    quantity_on_hand: int = 0
    warehouse_location: str | None = None
    reorder_threshold: int = 10


class RestockRequest(BaseModel):
    quantity: int
    requested_by: str | None = None


class InventoryItemResponse(BaseModel):
    id: int
    sku: str
    item_name: str | None
    unit_cost: float | None
    quantity_on_hand: int
    warehouse_location: str | None
    reorder_threshold: int
