from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.env import settings
from src.database.pg_client import init_pool, close_pool
from src.database.migrations import run_migrations
from src.utils.logger import get_logger

from src.tools.agencies import search as ag_search, get as ag_get, create as ag_create
from src.tools.backorders import search as bo_search, get as bo_get, create as bo_create
from src.tools.inventory import search as inv_search, get as inv_get, create as inv_create, restock as inv_restock
from src.tools.commissions import get as com_get, create as com_create
from src.tools.sdk_versions import get as sdk_get, create as sdk_create
from src.resources import agency_resource, inventory_resource
from src.prompts import backorder_analysis, commission_analysis

logger = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.POSTGRES_URL:
        await init_pool(settings.POSTGRES_URL)
        await run_migrations()
    else:
        logger.warning("POSTGRES_URL not set — DB features unavailable")
    yield
    await close_pool()


app = FastAPI(title="AI-Assistant MCP Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/mcp"

# Tools
for r in [ag_search.router, ag_get.router, ag_create.router]:
    app.include_router(r, prefix=PREFIX, tags=["agencies"])

for r in [bo_search.router, bo_get.router, bo_create.router]:
    app.include_router(r, prefix=PREFIX, tags=["backorders"])

for r in [inv_search.router, inv_get.router, inv_create.router, inv_restock.router]:
    app.include_router(r, prefix=PREFIX, tags=["inventory"])

for r in [com_get.router, com_create.router]:
    app.include_router(r, prefix=PREFIX, tags=["commissions"])

for r in [sdk_get.router, sdk_create.router]:
    app.include_router(r, prefix=PREFIX, tags=["sdk_versions"])

# Resources
app.include_router(agency_resource.router, prefix=PREFIX)
app.include_router(inventory_resource.router, prefix=PREFIX)

# Prompts
app.include_router(backorder_analysis.router, prefix=PREFIX)
app.include_router(commission_analysis.router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp", "db": bool(settings.POSTGRES_URL)}
