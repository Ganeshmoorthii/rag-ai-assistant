from pydantic import BaseModel


class CommissionCreate(BaseModel):
    agency_id: int
    order_type: str          # BILL-RESTOCK | BILL-ONLY | RESTOCK-ONLY
    item_cost: float
    period_month: int
    period_year: int


class CommissionResponse(BaseModel):
    id: int
    agency_id: int
    order_type: str
    item_cost: float
    commission_amount: float
    period_month: int
    period_year: int
    settled: bool
