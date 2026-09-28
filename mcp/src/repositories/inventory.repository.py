from src.database.pg_client import fetch, fetchrow, execute


async def find_all(low_stock: bool = False) -> list[dict]:
    if low_stock:
        return await fetch(
            "SELECT * FROM inventory_items WHERE quantity_on_hand <= reorder_threshold ORDER BY sku"
        )
    return await fetch("SELECT * FROM inventory_items ORDER BY sku")


async def find_by_sku(sku: str) -> dict | None:
    return await fetchrow("SELECT * FROM inventory_items WHERE sku = $1", sku)


async def find_by_id(item_id: int) -> dict | None:
    return await fetchrow("SELECT * FROM inventory_items WHERE id = $1", item_id)


async def create(sku: str, item_name: str | None, unit_cost: float | None,
                 quantity_on_hand: int, warehouse_location: str | None, reorder_threshold: int) -> dict:
    return await fetchrow(
        """INSERT INTO inventory_items
               (sku, item_name, unit_cost, quantity_on_hand, warehouse_location, reorder_threshold)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
        sku, item_name, unit_cost, quantity_on_hand, warehouse_location, reorder_threshold,
    )


async def add_quantity(sku: str, quantity: int) -> dict | None:
    return await fetchrow(
        "UPDATE inventory_items SET quantity_on_hand = quantity_on_hand + $1 WHERE sku = $2 RETURNING *",
        quantity, sku,
    )


async def log_restock(item_id: int, requested_by: str | None, quantity: int) -> None:
    await execute(
        "INSERT INTO restock_requests (item_id, requested_by, quantity, sdk_version) VALUES ($1, $2, $3, 'v3')",
        item_id, requested_by, quantity,
    )


async def delete(sku: str) -> None:
    await execute("DELETE FROM inventory_items WHERE sku = $1", sku)
