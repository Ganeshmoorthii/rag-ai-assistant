from fastapi import HTTPException


class NotFoundError(HTTPException):
    def __init__(self, resource: str, identifier: str | int):
        super().__init__(status_code=404, detail=f"{resource} '{identifier}' not found")


class ConflictError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


class ValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=422, detail=detail)


class DatabaseError(HTTPException):
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(status_code=500, detail=detail)
