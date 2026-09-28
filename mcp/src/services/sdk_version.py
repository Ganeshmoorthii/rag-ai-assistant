from src.repositories import sdk_version as repo
from src.schemas.sdk_version import SDKVersionCreate
from src.utils.errors import NotFoundError


async def list_versions(function_name: str | None = None, deprecated: bool | None = None) -> list[dict]:
    return await repo.find_all(function_name, deprecated)


async def get_current_version(function_name: str) -> dict:
    """Returns latest non-deprecated signature — resolves v2/v3 ambiguity."""
    row = await repo.find_current(function_name)
    if not row:
        raise NotFoundError("SDK function", function_name)
    return row


async def upsert_version(body: SDKVersionCreate) -> dict:
    return await repo.upsert(
        body.function_name, body.version, body.signature,
        body.deprecated, body.deprecation_note,
    )


async def deprecate_version(sdk_id: int, note: str | None = None) -> dict:
    row = await repo.deprecate(sdk_id, note)
    if not row:
        raise NotFoundError("SDK version", sdk_id)
    return row


async def delete_version(sdk_id: int) -> None:
    await repo.delete(sdk_id)
