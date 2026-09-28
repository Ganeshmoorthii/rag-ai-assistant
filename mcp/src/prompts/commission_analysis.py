from fastapi import APIRouter

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/commission-analysis")
async def commission_analysis_prompt(period_month: int | None = None, period_year: int | None = None):
    """Returns a structured prompt template for agent commission reconciliation."""
    period = f"{period_month}/{period_year}" if period_month and period_year else "the current period"
    return {
        "prompt": (
            f"Reconcile unsettled commissions for {period}. "
            "Commission rule: commission_amount = item_cost × 1.4 for BILL-RESTOCK orders. "
            "BILL-ONLY orders are counted as revenue. RESTOCK-ONLY orders are not. "
            "List all unsettled records, verify the calculation, then mark each as settled."
        ),
        "tools_needed": ["get_commissions", "settle_commission"],
    }
