from src.repositories import agency as repo
from src.schemas.agency.schema import AgencyCreate, AgencyUpdate
from src.utils.errors import NotFoundError, ConflictError


async def list_agencies(active_only: bool = True) -> list[dict]:
    return await repo.find_all(active_only)


async def get_agency(agency_code: str) -> dict:
    row = await repo.find_by_code(agency_code)
    if not row:
        raise NotFoundError("Agency", agency_code)
    return row


async def create_agency(body: AgencyCreate) -> dict:
    existing = await repo.find_by_code(body.agency_code)
    if existing:
        raise ConflictError(f"Agency '{body.agency_code}' already exists")
    return await repo.create(body.agency_code, body.agency_name, body.is_loaner, body.region)


async def update_agency(agency_id: int, body: AgencyUpdate) -> dict:
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise ValueError("No fields to update")
    row = await repo.update(agency_id, fields)
    if not row:
        raise NotFoundError("Agency", agency_id)
    return row


async def delete_agency(agency_id: int) -> None:
    row = await repo.find_by_id(agency_id)
    if not row:
        raise NotFoundError("Agency", agency_id)
    await repo.delete(agency_id)
