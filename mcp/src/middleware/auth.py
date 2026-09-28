from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.env import settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        if settings.API_SECRET:
            key = request.headers.get("x-api-key", "")
            if key != settings.API_SECRET:
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing x-api-key"})

        return await call_next(request)
