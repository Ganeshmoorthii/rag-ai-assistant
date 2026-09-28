from fastapi import APIRouter
from src.services import commission as svc

router = APIRouter()


@router.get("/commissions")
async def get_commissions(agency_id: int | None = None, settled: bool | None = None):
    return await svc.list_commissions(agency_id, settled)


@router.patch("/commissions/{commission_id}/settle")
async def settle_commission(commission_id: int):
    return await svc.settle_commission(commission_id)
