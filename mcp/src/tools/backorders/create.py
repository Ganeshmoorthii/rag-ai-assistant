from fastapi import APIRouter
from src.schemas.backorder import BackorderCreate, BackorderUpdate
from src.services import backorder as svc

router = APIRouter()


@router.post("/backorders", status_code=201)
async def create_backorder(body: BackorderCreate):
    return await svc.create_backorder(body)


@router.patch("/backorders/{backorder_id}")
async def update_backorder(backorder_id: int, body: BackorderUpdate):
    return await svc.update_backorder(backorder_id, body)


@router.delete("/backorders/{backorder_id}", status_code=204)
async def delete_backorder(backorder_id: int):
    await svc.delete_backorder(backorder_id)
