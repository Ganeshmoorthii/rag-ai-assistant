from pydantic import BaseModel


class AgencyCreate(BaseModel):
    agency_code: str
    agency_name: str | None = None
    is_loaner: bool = False
    region: str | None = None


class AgencyUpdate(BaseModel):
    agency_name: str | None = None
    is_loaner: bool | None = None
    region: str | None = None
    active: bool | None = None


class AgencyResponse(BaseModel):
    id: int
    agency_code: str
    agency_name: str | None
    is_loaner: bool
    region: str | None
    active: bool
