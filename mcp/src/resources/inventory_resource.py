from fastapi import APIRouter
from src.repositories import inventory as repo

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/inventory/low-stock")
async def low_stock_summary():
    """MCP resource — items below reorder threshold, for agent proactive alerts."""
    rows = await repo.find_all(low_stock=True)
    return {
        "resource": "inventory_low_stock",
        "count": len(rows),
        "data": rows,
    }
