from src.database.pg_client import fetch, fetchrow, execute


async def find_all(active_only: bool = True) -> list[dict]:
    if active_only:
        return await fetch("SELECT * FROM agencies WHERE active = true ORDER BY agency_code")
    return await fetch("SELECT * FROM agencies ORDER BY agency_code")


async def find_by_code(agency_code: str) -> dict | None:
    return await fetchrow("SELECT * FROM agencies WHERE agency_code = $1", agency_code)


async def find_by_id(agency_id: int) -> dict | None:
    return await fetchrow("SELECT * FROM agencies WHERE id = $1", agency_id)


async def create(agency_code: str, agency_name: str | None, is_loaner: bool, region: str | None) -> dict:
    return await fetchrow(
        """INSERT INTO agencies (agency_code, agency_name, is_loaner, region)
           VALUES ($1, $2, $3, $4) RETURNING *""",
        agency_code, agency_name, is_loaner, region,
    )


async def update(agency_id: int, fields: dict) -> dict | None:
    cols, vals, idx = [], [], 1
    for col, val in fields.items():
        cols.append(f"{col} = ${idx}"); vals.append(val); idx += 1
    vals.append(agency_id)
    return await fetchrow(
        f"UPDATE agencies SET {', '.join(cols)} WHERE id = ${idx} RETURNING *", *vals
    )


async def delete(agency_id: int) -> None:
    await execute("DELETE FROM agencies WHERE id = $1", agency_id)
