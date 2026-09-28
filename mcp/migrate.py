"""Standalone migration runner — run from the mcp/ directory."""
import asyncio
import sys
from src.config.env import settings
from src.database.pg_client import init_pool, close_pool
from src.database.migrations import run_migrations


async def main() -> None:
    if not settings.POSTGRES_URL:
        print("ERROR: POSTGRES_URL is not set in .env", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to: {settings.POSTGRES_URL[:40]}...")
    await init_pool(settings.POSTGRES_URL)
    await run_migrations()
    await close_pool()
    print("Migrations applied successfully.")


if __name__ == "__main__":
    asyncio.run(main())
