from src.database.pg_client import execute
from src.utils.logger import get_logger

logger = get_logger("migrations")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agencies (
    id              SERIAL PRIMARY KEY,
    agency_code     TEXT UNIQUE NOT NULL,
    agency_name     TEXT,
    is_loaner       BOOLEAN DEFAULT false,
    region          TEXT,
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id                  SERIAL PRIMARY KEY,
    sku                 TEXT UNIQUE NOT NULL,
    item_name           TEXT,
    unit_cost           DECIMAL(10,2),
    quantity_on_hand    INT DEFAULT 0,
    warehouse_location  TEXT,
    reorder_threshold   INT DEFAULT 10,
    created_at          TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backorders (
    id                  SERIAL PRIMARY KEY,
    agency_id           INT REFERENCES agencies(id) ON DELETE CASCADE,
    item_sku            TEXT NOT NULL,
    quantity_ordered    INT NOT NULL,
    quantity_fulfilled  INT DEFAULT 0,
    status              TEXT DEFAULT 'open',
    created_at          TIMESTAMP DEFAULT now(),
    updated_at          TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restock_requests (
    id              SERIAL PRIMARY KEY,
    item_id         INT REFERENCES inventory_items(id) ON DELETE CASCADE,
    requested_by    TEXT,
    quantity        INT NOT NULL,
    sdk_version     TEXT DEFAULT 'v3',
    status          TEXT DEFAULT 'pending',
    requested_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS commissions (
    id                  SERIAL PRIMARY KEY,
    agency_id           INT REFERENCES agencies(id) ON DELETE CASCADE,
    order_type          TEXT,
    item_cost           DECIMAL(10,2),
    commission_amount   DECIMAL(10,2),
    period_month        INT,
    period_year         INT,
    settled             BOOLEAN DEFAULT false,
    created_at          TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sdk_versions (
    id                  SERIAL PRIMARY KEY,
    function_name       TEXT NOT NULL,
    version             TEXT NOT NULL,
    signature           TEXT,
    deprecated          BOOLEAN DEFAULT false,
    deprecation_note    TEXT,
    UNIQUE (function_name, version)
);
"""


async def run_migrations() -> None:
    await execute(_SCHEMA)
    logger.info("migrations applied")
