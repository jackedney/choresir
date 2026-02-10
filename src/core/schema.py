"""SQLite schema management (code-first approach)."""

import logging

from src.core import module_registry
from src.core.db_client import get_connection


logger = logging.getLogger(__name__)


CORE_TABLE_SCHEMAS = {
    "members": """CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        phone TEXT NOT NULL UNIQUE,
        name TEXT,
        role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
        status TEXT NOT NULL DEFAULT 'pending_name' CHECK (status IN ('pending_name', 'active'))
    )""",
    "processed_messages": """CREATE TABLE IF NOT EXISTS processed_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        message_id TEXT NOT NULL UNIQUE,
        from_phone TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        success INTEGER DEFAULT 0,
        error_message TEXT
    )""",
    "house_config": """CREATE TABLE IF NOT EXISTS house_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        name TEXT NOT NULL,
        group_chat_id TEXT,
        activation_key TEXT
    )""",
    "bot_messages": """CREATE TABLE IF NOT EXISTS bot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        message_id TEXT NOT NULL UNIQUE,
        text TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        sent_at TEXT NOT NULL
    )""",
    "group_context": """CREATE TABLE IF NOT EXISTS group_context (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        group_id TEXT NOT NULL,
        sender_phone TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        content TEXT NOT NULL,
        is_bot INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    "join_sessions": """CREATE TABLE IF NOT EXISTS join_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        phone TEXT NOT NULL,
        house_name TEXT NOT NULL,
        step TEXT NOT NULL,
        password_attempts_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    "workflows": """CREATE TABLE IF NOT EXISTS workflows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        type TEXT NOT NULL CHECK (type IN ('deletion_approval', 'task_verification')),
        status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),
        requester_user_id INTEGER NOT NULL REFERENCES members(id),
        requester_name TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        resolved_at TEXT,
        resolver_user_id INTEGER REFERENCES members(id),
        resolver_name TEXT,
        reason TEXT,
        metadata TEXT
    )""",
}

CORE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows (status)",
    "CREATE INDEX IF NOT EXISTS idx_workflows_requester_user_id ON workflows (requester_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workflows_expires_at ON workflows (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_group_context_group_id ON group_context (group_id)",
    "CREATE INDEX IF NOT EXISTS idx_group_context_expires_at ON group_context (expires_at)",
]


TABLES = [
    "members",
    "processed_messages",
    "house_config",
    "bot_messages",
    "group_context",
    "join_sessions",
    "workflows",
]


async def init_db(*, db_path: str | None = None) -> None:
    """Initialize the database schema by creating all tables and indexes.

    This function is idempotent - it can be called multiple times without errors.

    Creates core tables first, then module tables from the registry.

    Args:
        db_path: Optional custom database path for test flexibility.
                  If not provided, uses the default path from settings.

    Raises:
        RuntimeError: If schema initialization fails
    """
    logger.info("Initializing database schema...")

    try:
        conn = await get_connection(db_path=db_path)

        for table_name, table_schema in CORE_TABLE_SCHEMAS.items():
            await conn.execute(table_schema)
            logger.debug("Created core table: %s", table_name)

        for index_sql in CORE_INDEXES:
            await conn.execute(index_sql)
            logger.debug("Created core index: %s", index_sql[:50])

        module_schemas = module_registry.get_all_table_schemas()
        for table_name, table_schema in module_schemas.items():
            await conn.execute(table_schema)
            logger.debug("Created module table: %s", table_name)

        module_indexes = module_registry.get_all_indexes()
        for index_sql in module_indexes:
            await conn.execute(index_sql)
            logger.debug("Created module index: %s", index_sql[:50])

        await conn.commit()

        logger.info(
            "Database schema initialized successfully with %d core tables, %d module tables, and %d indexes",
            len(CORE_TABLE_SCHEMAS),
            len(module_schemas),
            len(CORE_INDEXES) + len(module_indexes),
        )
    except Exception as e:
        logger.error("Failed to initialize database schema: %s", e)
        msg = f"Database schema initialization failed: {e}"
        raise RuntimeError(msg) from e
