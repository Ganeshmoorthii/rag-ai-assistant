from pydantic import BaseModel


class BackorderCreate(BaseModel):
    agency_id: int
    item_sku: str
    quantity_ordered: int


class BackorderUpdate(BaseModel):
    quantity_fulfilled: int | None = None
    status: str | None = None          # open | partial | fulfilled | cancelled


class BackorderResponse(BaseModel):
    id: int
    agency_id: int
    item_sku: str
    quantity_ordered: int
    quantity_fulfilled: int
    status: str
