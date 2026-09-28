from src.repositories import commission as repo
from src.schemas.commission.schema import CommissionCreate
from src.utils.errors import NotFoundError, ValidationError

COMMISSION_MULTIPLIER = 1.4   # from Advita docs: commission = item_cost × 1.4
VALID_ORDER_TYPES = {"BILL-RESTOCK", "BILL-ONLY", "RESTOCK-ONLY"}


async def list_commissions(agency_id: int | None = None, settled: bool | None = None) -> list[dict]:
    return await repo.find_all(agency_id, settled)


async def create_commission(body: CommissionCreate) -> dict:
    if body.order_type not in VALID_ORDER_TYPES:
        raise ValidationError(f"order_type must be one of {VALID_ORDER_TYPES}")
    commission_amount = round(body.item_cost * COMMISSION_MULTIPLIER, 2)
    return await repo.create(
        body.agency_id, body.order_type, body.item_cost,
        commission_amount, body.period_month, body.period_year,
    )


async def settle_commission(commission_id: int) -> dict:
    row = await repo.settle(commission_id)
    if not row:
        raise NotFoundError("Commission", commission_id)
    return row


async def delete_commission(commission_id: int) -> None:
    await repo.delete(commission_id)
