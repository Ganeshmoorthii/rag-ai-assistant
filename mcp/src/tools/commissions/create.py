from fastapi import APIRouter
from src.schemas.commission import CommissionCreate
from src.services import commission as svc

router = APIRouter()


@router.post("/commissions", status_code=201)
async def create_commission(body: CommissionCreate):
    """Auto-calculates commission_amount = item_cost × 1.4 (Advita billing rule)."""
    return await svc.create_commission(body)


@router.delete("/commissions/{commission_id}", status_code=204)
async def delete_commission(commission_id: int):
    await svc.delete_commission(commission_id)
