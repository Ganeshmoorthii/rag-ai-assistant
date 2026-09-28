from pydantic import BaseModel


class SDKVersionCreate(BaseModel):
    function_name: str
    version: str             # "v2" | "v3"
    signature: str | None = None
    deprecated: bool = False
    deprecation_note: str | None = None


class SDKVersionResponse(BaseModel):
    id: int
    function_name: str
    version: str
    signature: str | None
    deprecated: bool
    deprecation_note: str | None
