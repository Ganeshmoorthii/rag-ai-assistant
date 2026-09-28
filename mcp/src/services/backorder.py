from src.repositories import backorder as repo
from src.schemas.backorder import BackorderCreate, BackorderUpdate
from src.utils.errors import NotFoundError, ValidationError

VALID_STATUSES = {"open", "partial", "fulfilled", "cancelled"}


async def list_backorders(status: str | None = None, agency_id: int | None = None) -> list[dict]:
    if status and status not in VALID_STATUSES:
        raise ValidationError(f"status must be one of {VALID_STATUSES}")
    return await repo.find_all(status, agency_id)


async def get_backorder(backorder_id: int) -> dict:
    row = await repo.find_by_id(backorder_id)
    if not row:
        raise NotFoundError("Backorder", backorder_id)
    return row


async def create_backorder(body: BackorderCreate) -> dict:
    if body.quantity_ordered <= 0:
        raise ValidationError("quantity_ordered must be greater than 0")
    return await repo.create(body.agency_id, body.item_sku, body.quantity_ordered)


async def update_backorder(backorder_id: int, body: BackorderUpdate) -> dict:
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise ValidationError("No fields to update")
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        raise ValidationError(f"status must be one of {VALID_STATUSES}")
    row = await repo.update(backorder_id, fields)
    if not row:
        raise NotFoundError("Backorder", backorder_id)
    return row


async def delete_backorder(backorder_id: int) -> None:
    row = await repo.find_by_id(backorder_id)
    if not row:
        raise NotFoundError("Backorder", backorder_id)
    await repo.delete(backorder_id)
