from fastapi import APIRouter
from src.services import agency as svc

router = APIRouter()


@router.get("/agencies/{agency_code}")
async def get_agency(agency_code: str):
    return await svc.get_agency(agency_code)
