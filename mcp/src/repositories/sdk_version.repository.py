from src.database.pg_client import fetch, fetchrow, execute


async def find_all(function_name: str | None = None, deprecated: bool | None = None) -> list[dict]:
    conditions, values, idx = [], [], 1
    if function_name:
        conditions.append(f"function_name ILIKE ${idx}"); values.append(f"%{function_name}%"); idx += 1
    if deprecated is not None:
        conditions.append(f"deprecated = ${idx}"); values.append(deprecated); idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return await fetch(f"SELECT * FROM sdk_versions {where} ORDER BY function_name, version", *values)


async def find_current(function_name: str) -> dict | None:
    return await fetchrow(
        """SELECT * FROM sdk_versions
           WHERE function_name ILIKE $1 AND deprecated = false
           ORDER BY version DESC LIMIT 1""",
        function_name,
    )


async def upsert(function_name: str, version: str, signature: str | None,
                 deprecated: bool, deprecation_note: str | None) -> dict:
    return await fetchrow(
        """INSERT INTO sdk_versions (function_name, version, signature, deprecated, deprecation_note)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (function_name, version) DO UPDATE
               SET signature = EXCLUDED.signature,
                   deprecated = EXCLUDED.deprecated,
                   deprecation_note = EXCLUDED.deprecation_note
           RETURNING *""",
        function_name, version, signature, deprecated, deprecation_note,
    )


async def deprecate(sdk_id: int, note: str | None) -> dict | None:
    return await fetchrow(
        "UPDATE sdk_versions SET deprecated = true, deprecation_note = $1 WHERE id = $2 RETURNING *",
        note, sdk_id,
    )


async def delete(sdk_id: int) -> None:
    await execute("DELETE FROM sdk_versions WHERE id = $1", sdk_id)
