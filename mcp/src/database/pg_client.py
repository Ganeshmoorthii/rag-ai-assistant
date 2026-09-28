import asyncpg
from src.utils.logger import get_logger

logger = get_logger("pg_client")
_pool: asyncpg.Pool | None = None


async def init_pool(postgres_url: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(postgres_url, min_size=2, max_size=10, command_timeout=30)
    logger.info("connection pool ready")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool


async def fetch(sql: str, *args) -> list[dict]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, *args)]


async def fetchrow(sql: str, *args) -> dict | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(sql, *args)
        return dict(row) if row else None


async def execute(sql: str, *args) -> str:
    if not _pool:
        return ""
    async with _pool.acquire() as conn:
        return await conn.execute(sql, *args)
