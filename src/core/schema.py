"""SQLite schema management (code-first approach)."""

import logging

from src.core.db_client import get_connection


logger = logging.getLogger(__name__)


TABLE_SCHEMAS = {
    "members": """CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        phone TEXT NOT NULL UNIQUE,
        name TEXT,
        role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
        status TEXT NOT NULL DEFAULT 'pending_name' CHECK (status IN ('pending_name', 'active'))
    )""",
    "chores": """CREATE TABLE IF NOT EXISTS chores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        title TEXT NOT NULL,
        description TEXT,
        schedule_cron TEXT NOT NULL,
        assigned_to INTEGER REFERENCES members(id),
        current_state TEXT NOT NULL CHECK (
            current_state IN (
                'TODO', 'PENDING_VERIFICATION', 'COMPLETED',
                'CONFLICT', 'DEADLOCK', 'ARCHIVED'
            )
        ),
        deadline TEXT NOT NULL
    )""",
    "logs": """CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        chore_id INTEGER REFERENCES chores(id),
        user_id INTEGER REFERENCES members(id),
        action TEXT,
        notes TEXT,
        timestamp TEXT,
        original_assignee_id INTEGER REFERENCES members(id),
        actual_completer_id INTEGER REFERENCES members(id),
        is_swap INTEGER DEFAULT 0
    )""",
    "robin_hood_swaps": """CREATE TABLE IF NOT EXISTS robin_hood_swaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        user_id INTEGER NOT NULL REFERENCES members(id),
        week_start_date TEXT NOT NULL,
        takeover_count INTEGER NOT NULL,
        UNIQUE(user_id, week_start_date)
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
    "pantry_items": """CREATE TABLE IF NOT EXISTS pantry_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        name TEXT NOT NULL UNIQUE,
        quantity INTEGER,
        status TEXT NOT NULL CHECK (status IN ('IN_STOCK', 'LOW', 'OUT')),
        last_restocked TEXT
    )""",
    "shopping_list": """CREATE TABLE IF NOT EXISTS shopping_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        item_name TEXT NOT NULL,
        added_by INTEGER NOT NULL REFERENCES members(id),
        added_at TEXT NOT NULL,
        quantity INTEGER,
        notes TEXT
    )""",
    "personal_chores": """CREATE TABLE IF NOT EXISTS personal_chores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        owner_phone TEXT NOT NULL,
        title TEXT NOT NULL,
        recurrence TEXT,
        due_date TEXT,
        accountability_partner_phone TEXT,
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
        created_at TEXT NOT NULL
    )""",
    "personal_chore_logs": """CREATE TABLE IF NOT EXISTS personal_chore_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        personal_chore_id INTEGER NOT NULL REFERENCES personal_chores(id),
        owner_phone TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        verification_status TEXT NOT NULL CHECK (
            verification_status IN ('SELF_VERIFIED', 'PENDING', 'VERIFIED', 'REJECTED')
        ),
        accountability_partner_phone TEXT,
        partner_feedback TEXT,
        notes TEXT
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
        type TEXT NOT NULL CHECK (type IN ('deletion_approval', 'chore_verification', 'personal_verification')),
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


INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chores_assigned_to ON chores (assigned_to)",
    "CREATE INDEX IF NOT EXISTS idx_logs_chore_id ON logs (chore_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_original_assignee_id ON logs (original_assignee_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_actual_completer_id ON logs (actual_completer_id)",
    "CREATE INDEX IF NOT EXISTS idx_shopping_list_added_by ON shopping_list (added_by)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chores_owner_phone ON personal_chores (owner_phone)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chores_status ON personal_chores (status)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_logs_personal_chore_id ON personal_chore_logs (personal_chore_id)",
    "CREATE INDEX IF NOT EXISTS idx_personal_chore_logs_owner_phone ON personal_chore_logs (owner_phone)",
    "CREATE INDEX IF NOT EXISTS "
    "idx_personal_chore_logs_verification_status ON personal_chore_logs (verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows (status)",
    "CREATE INDEX IF NOT EXISTS idx_workflows_requester_user_id ON workflows (requester_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workflows_expires_at ON workflows (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_group_context_group_id ON group_context (group_id)",
    "CREATE INDEX IF NOT EXISTS idx_group_context_expires_at ON group_context (expires_at)",
]


TABLES = [
    "members",
    "chores",
    "logs",
    "robin_hood_swaps",
    "processed_messages",
    "pantry_items",
    "shopping_list",
    "personal_chores",
    "personal_chore_logs",
    "house_config",
    "bot_messages",
    "group_context",
    "join_sessions",
    "workflows",
]


async def init_db(*, db_path: str | None = None) -> None:
    """Initialize the database schema by creating all tables and indexes.

    This function is idempotent - it can be called multiple times without errors.

    Args:
        db_path: Optional custom database path for test flexibility.
                  If not provided, uses the default path from settings.

    Raises:
        RuntimeError: If schema initialization fails
    """
    logger.info("Initializing database schema...")

    try:
        conn = await get_connection(db_path=db_path)

        for table_name, table_schema in TABLE_SCHEMAS.items():
            await conn.execute(table_schema)
            logger.debug("Created table: %s", table_name)

        for index_sql in INDEXES:
            await conn.execute(index_sql)
            logger.debug("Created index: %s", index_sql[:50])

        await conn.commit()

        logger.info(
            "Database schema initialized successfully with %d tables and %d indexes", len(TABLE_SCHEMAS), len(INDEXES)
        )
    except Exception as e:
        logger.error("Failed to initialize database schema: %s", e)
        msg = f"Database schema initialization failed: {e}"
        raise RuntimeError(msg) from e
