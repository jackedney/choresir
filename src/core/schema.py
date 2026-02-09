"""SQLite schema management (code-first approach)."""

import logging
from pathlib import Path

import aiosqlite

from src.core.config import settings


logger = logging.getLogger(__name__)

# PocketBase to SQLite type mapping
# text -> TEXT, number -> REAL, bool -> INTEGER, date -> TEXT (ISO 8601),
# select -> TEXT, relation -> TEXT, json -> TEXT


# Standard columns for all tables
_STANDARD_COLUMNS = """
    id TEXT PRIMARY KEY,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
"""


# SQLite table definitions (CREATE TABLE statements)
# Each table has standard columns (id, created, updated) plus schema-specific columns
# Uses CREATE TABLE IF NOT EXISTS for idempotence
TABLE_SCHEMAS = {
    "members": f"""{_STANDARD_COLUMNS},
    phone TEXT NOT NULL UNIQUE,
    name TEXT,
    role TEXT NOT NULL,
    status TEXT NOT NULL
""",
    "chores": f"""{_STANDARD_COLUMNS},
    title TEXT NOT NULL,
    description TEXT,
    schedule_cron TEXT NOT NULL,
    assigned_to TEXT,
    current_state TEXT NOT NULL,
    deadline TEXT NOT NULL
""",
    "logs": f"""{_STANDARD_COLUMNS},
    chore_id TEXT,
    user_id TEXT,
    action TEXT,
    notes TEXT,
    timestamp TEXT,
    original_assignee_id TEXT,
    actual_completer_id TEXT,
    is_swap INTEGER
""",
    "robin_hood_swaps": f"""{_STANDARD_COLUMNS},
    user_id TEXT NOT NULL,
    week_start_date TEXT NOT NULL,
    takeover_count REAL NOT NULL
""",
    "processed_messages": f"""{_STANDARD_COLUMNS},
    message_id TEXT NOT NULL UNIQUE,
    from_phone TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    success INTEGER,
    error_message TEXT
""",
    "pantry_items": f"""{_STANDARD_COLUMNS},
    name TEXT NOT NULL UNIQUE,
    quantity REAL,
    status TEXT NOT NULL,
    last_restocked TEXT
""",
    "shopping_list": f"""{_STANDARD_COLUMNS},
    item_name TEXT NOT NULL,
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    quantity REAL,
    notes TEXT
""",
    "personal_chores": f"""{_STANDARD_COLUMNS},
    owner_phone TEXT NOT NULL,
    title TEXT NOT NULL,
    recurrence TEXT,
    due_date TEXT,
    accountability_partner_phone TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
""",
    "personal_chore_logs": f"""{_STANDARD_COLUMNS},
    personal_chore_id TEXT NOT NULL,
    owner_phone TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    accountability_partner_phone TEXT,
    partner_feedback TEXT,
    notes TEXT
""",
    "house_config": f"""{_STANDARD_COLUMNS},
    name TEXT NOT NULL,
    group_chat_id TEXT,
    activation_key TEXT
""",
    "bot_messages": f"""{_STANDARD_COLUMNS},
    message_id TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sent_at TEXT NOT NULL
""",
    "group_context": f"""{_STANDARD_COLUMNS},
    group_id TEXT NOT NULL,
    sender_phone TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_bot INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
""",
    "workflows": f"""{_STANDARD_COLUMNS},
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    requester_user_id TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    resolver_user_id TEXT,
    resolver_name TEXT,
    reason TEXT,
    metadata TEXT
""",
}


# Index definitions (CREATE INDEX statements)
# Uses CREATE INDEX IF NOT EXISTS for idempotence
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chores_assigned_to ON chores (assigned_to)",
    "CREATE INDEX IF NOT EXISTS idx_logs_chore_id ON logs (chore_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_original_assignee_id ON logs (original_assignee_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_actual_completer_id ON logs (actual_completer_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rhswaps_user_week ON robin_hood_swaps (user_id, week_start_date)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_owner ON personal_chores (owner_phone)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_status ON personal_chores (status)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_logs_chore ON personal_chore_logs (personal_chore_id)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_logs_owner ON personal_chore_logs (owner_phone)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_logs_verification ON personal_chore_logs (verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflows (status)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_requester ON workflows (requester_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_expires_at ON workflows (expires_at)",
]


# Central list of all tables in the schema
TABLES = list(TABLE_SCHEMAS.keys())

# Backward compatibility exports for US-006, US-008, etc.
COLLECTIONS = TABLES


async def init_db(*, db_path: str | None = None) -> None:
    """Initialize SQLite database with all tables and indexes.

    Creates tables for all collections defined in TABLE_SCHEMAS if they don't exist.
    Uses CREATE TABLE IF NOT EXISTS to make this idempotent.

    Args:
        db_path: Optional path to SQLite database file. If not provided, uses settings.pocketbase_url
            (will be replaced with sqlite_db_path in US-005).

    Raises:
        RuntimeError: If database initialization fails
    """
    if db_path is None:
        db_path = settings.pocketbase_url
        if db_path.startswith("http://") or db_path.startswith("https://"):
            # Temporary: use local data directory until US-005 adds sqlite_db_path config
            db_dir = Path(__file__).parent.parent.parent / "data"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "choresir.db")

    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")

            logger.info("Initializing SQLite database tables")

            for table_name, table_schema in TABLE_SCHEMAS.items():
                await conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({table_schema})")

            for index_sql in INDEXES:
                await conn.execute(index_sql)

            await conn.commit()

            logger.info("SQLite database initialized successfully", extra={"tables": TABLES, "indexes": len(INDEXES)})
    except Exception as e:
        msg = f"Failed to initialize database: {e}"
        logger.error("Database initialization failed", extra={"error": str(e)})
        raise RuntimeError(msg) from e


# ruff: noqa: ARG001 - Arguments are for backward compatibility with PocketBase API
async def sync_schema(
    *,
    admin_email: str = "",
    admin_password: str = "",
    pocketbase_url: str | None = None,
) -> None:
    """Backward compatibility wrapper for sync_schema.

    This was the PocketBase schema sync function. Now it's a wrapper around init_db()
    for compatibility with existing code. The admin_email, admin_password, and pocketbase_url
    parameters are ignored since SQLite doesn't require authentication.

    Args:
        admin_email: Ignored (kept for API compatibility)
        admin_password: Ignored (kept for API compatibility)
        pocketbase_url: Ignored (kept for API compatibility)
    """
    await init_db()
