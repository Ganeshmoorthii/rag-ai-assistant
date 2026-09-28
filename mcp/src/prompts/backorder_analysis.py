from fastapi import APIRouter

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/backorder-analysis")
async def backorder_analysis_prompt(agency_code: str | None = None):
    """Returns a structured prompt template for agent backorder analysis."""
    context = f"for agency {agency_code}" if agency_code else "across all agencies"
    return {
        "prompt": (
            f"Analyse open backorders {context}. "
            "For each backorder: check current inventory level, determine if fulfilment is possible, "
            "and recommend either: (1) fulfil now, (2) raise a restock request, or (3) escalate. "
            "Use the getBackorders SDK v3 signature: getBackorders({ agencyId, options })."
        ),
        "tools_needed": ["search_backorders", "get_inventory_item", "restock_item"],
    }
