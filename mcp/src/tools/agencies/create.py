from fastapi import APIRouter
from src.schemas.agency import AgencyCreate, AgencyUpdate
from src.services import agency as svc

router = APIRouter()


@router.post("/agencies", status_code=201)
async def create_agency(body: AgencyCreate):
    return await svc.create_agency(body)


@router.patch("/agencies/{agency_id}")
async def update_agency(agency_id: int, body: AgencyUpdate):
    return await svc.update_agency(agency_id, body)


@router.delete("/agencies/{agency_id}", status_code=204)
async def delete_agency(agency_id: int):
    await svc.delete_agency(agency_id)
