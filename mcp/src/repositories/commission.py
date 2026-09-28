from src.database.pg_client import fetch, fetchrow, execute


async def find_all(agency_id: int | None = None, settled: bool | None = None) -> list[dict]:
    conditions, values, idx = [], [], 1
    if agency_id is not None:
        conditions.append(f"agency_id = ${idx}"); values.append(agency_id); idx += 1
    if settled is not None:
        conditions.append(f"settled = ${idx}"); values.append(settled); idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return await fetch(f"SELECT * FROM commissions {where} ORDER BY created_at DESC", *values)


async def create(agency_id: int, order_type: str, item_cost: float,
                 commission_amount: float, period_month: int, period_year: int) -> dict:
    return await fetchrow(
        """INSERT INTO commissions
               (agency_id, order_type, item_cost, commission_amount, period_month, period_year)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
        agency_id, order_type, item_cost, commission_amount, period_month, period_year,
    )


async def settle(commission_id: int) -> dict | None:
    return await fetchrow(
        "UPDATE commissions SET settled = true WHERE id = $1 RETURNING *", commission_id
    )


async def delete(commission_id: int) -> None:
    await execute("DELETE FROM commissions WHERE id = $1", commission_id)
