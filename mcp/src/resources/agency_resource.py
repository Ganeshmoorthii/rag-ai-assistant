from fastapi import APIRouter
from src.repositories import agency as repo

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/agencies/summary")
async def agency_summary():
    """MCP resource — full agency list for agent context loading."""
    rows = await repo.find_all(active_only=True)
    return {
        "resource": "agencies",
        "count": len(rows),
        "data": rows,
    }
