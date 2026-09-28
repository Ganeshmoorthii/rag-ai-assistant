from src.database.pg_client import fetch, fetchrow, execute


async def find_all(status: str | None = None, agency_id: int | None = None) -> list[dict]:
    conditions, values, idx = [], [], 1
    if status:
        conditions.append(f"status = ${idx}"); values.append(status); idx += 1
    if agency_id:
        conditions.append(f"agency_id = ${idx}"); values.append(agency_id); idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return await fetch(f"SELECT * FROM backorders {where} ORDER BY created_at DESC", *values)


async def find_by_id(backorder_id: int) -> dict | None:
    return await fetchrow("SELECT * FROM backorders WHERE id = $1", backorder_id)


async def create(agency_id: int, item_sku: str, quantity_ordered: int) -> dict:
    return await fetchrow(
        """INSERT INTO backorders (agency_id, item_sku, quantity_ordered)
           VALUES ($1, $2, $3) RETURNING *""",
        agency_id, item_sku, quantity_ordered,
    )


async def update(backorder_id: int, fields: dict) -> dict | None:
    cols, vals, idx = [], [], 1
    for col, val in fields.items():
        cols.append(f"{col} = ${idx}"); vals.append(val); idx += 1
    cols.append("updated_at = now()")
    vals.append(backorder_id)
    return await fetchrow(
        f"UPDATE backorders SET {', '.join(cols)} WHERE id = ${idx} RETURNING *", *vals
    )


async def delete(backorder_id: int) -> None:
    await execute("DELETE FROM backorders WHERE id = $1", backorder_id)
