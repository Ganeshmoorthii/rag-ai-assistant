from datetime import datetime
from pydantic import BaseModel


class AuthTokenCreate(BaseModel):
    token_name: str
    scope: str               # e.g. "revenue:read", "inventory:write"
    issued_to: str
    expires_at: datetime | None = None


class AuthTokenResponse(BaseModel):
    id: int
    token_name: str
    scope: str
    issued_to: str
    expires_at: datetime | None
    revoked: bool
