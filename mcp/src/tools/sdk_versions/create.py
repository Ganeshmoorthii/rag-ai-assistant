from fastapi import APIRouter
from src.schemas.sdk_version import SDKVersionCreate
from src.services import sdk_version as svc

router = APIRouter()


@router.post("/sdk-versions", status_code=201)
async def upsert_version(body: SDKVersionCreate):
    return await svc.upsert_version(body)


@router.patch("/sdk-versions/{sdk_id}/deprecate")
async def deprecate_version(sdk_id: int, note: str | None = None):
    return await svc.deprecate_version(sdk_id, note)


@router.delete("/sdk-versions/{sdk_id}", status_code=204)
async def delete_version(sdk_id: int):
    await svc.delete_version(sdk_id)
