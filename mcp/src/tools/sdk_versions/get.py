from fastapi import APIRouter
from src.services import sdk_version as svc

router = APIRouter()


@router.get("/sdk-versions")
async def list_versions(function_name: str | None = None, deprecated: bool | None = None):
    return await svc.list_versions(function_name, deprecated)


@router.get("/sdk-versions/{function_name}/current")
async def get_current_version(function_name: str):
    """Resolves the v2/v3 confusion — returns only the active non-deprecated signature."""
    return await svc.get_current_version(function_name)
