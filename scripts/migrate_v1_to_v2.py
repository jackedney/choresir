"""Migration script v1 to v2: Migrate chores/personal_chores to unified tasks/task_logs tables.

This script migrates data from the old schema (chores, personal_chores, logs, personal_chore_logs)
to the new unified schema (tasks, task_logs).

Old Tables:
  - chores (shared chores)
  - logs (chore activity logs)
  - personal_chores (personal tasks)
  - personal_chore_logs (personal task logs)
  - workflows (type: 'chore_verification', 'personal_verification')

New Tables:
  - tasks (unified task table)
  - task_logs (unified log table)
  - workflows (type: 'task_verification')
  - house_config (add schema_version field)

The migration is idempotent - safe to re-run multiple times.
"""

import argparse
import asyncio
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite

from src.core.config import settings


logger = logging.getLogger(__name__)


OLD_TABLES = [
    "chores",
    "logs",
    "personal_chores",
    "personal_chore_logs",
]


NEW_TABLES = [
    "tasks",
    "task_logs",
]


OLD_WORKFLOW_TYPES = [
    "chore_verification",
    "personal_verification",
]


async def create_backup(*, db_path: Path) -> Path:
    """Create a backup of the database before migration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info("Created backup at: %s", backup_path)
    return backup_path


async def table_exists(conn: aiosqlite.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return await cursor.fetchone() is not None


async def get_member_id_by_phone(conn: aiosqlite.Connection, phone: str) -> int | None:
    """Get member ID by phone number."""
    cursor = await conn.execute("SELECT id FROM members WHERE phone=?", (phone,))
    row = await cursor.fetchone()
    return row[0] if row else None


async def migrate_chores_to_tasks(conn: aiosqlite.Connection) -> int:
    """Migrate chores table to tasks table with scope='shared' and verification='peer'."""
    if not await table_exists(conn, "chores"):
        logger.info("Old 'chores' table does not exist, skipping migration")
        return 0

    cursor = await conn.execute(
        """SELECT id, created, updated, title, description, schedule_cron,
                  assigned_to, current_state, deadline
           FROM chores"""
    )
    chores = await cursor.fetchall()

    migrated = 0
    for chore in chores:
        (
            old_id,
            created,
            updated,
            title,
            description,
            schedule_cron,
            assigned_to,
            current_state,
            deadline,
        ) = chore

        await conn.execute(
            """INSERT OR IGNORE INTO tasks
               (id, created, updated, title, description, schedule_cron,
                assigned_to, scope, verification, current_state, deadline, module)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'shared', 'peer', ?, ?, 'task')""",
            (old_id, created, updated, title, description, schedule_cron, assigned_to, current_state, deadline),
        )
        migrated += 1

    await conn.commit()
    logger.info("Migrated %d chores to tasks (scope='shared', verification='peer')", migrated)
    return migrated


async def migrate_personal_chores_to_tasks(conn: aiosqlite.Connection) -> int:
    """Migrate personal_chores table to tasks table with scope='personal' and verification='partner'."""
    if not await table_exists(conn, "personal_chores"):
        logger.info("Old 'personal_chores' table does not exist, skipping migration")
        return 0

    cursor = await conn.execute(
        """SELECT id, created, updated, owner_phone, title, recurrence,
                  due_date, accountability_partner_phone, status, created_at
           FROM personal_chores"""
    )
    personal_chores = await cursor.fetchall()

    migrated = 0
    for pc in personal_chores:
        (
            old_id,
            created,
            updated,
            owner_phone,
            title,
            recurrence,
            due_date,
            accountability_partner_phone,
            status,
            _created_at,
        ) = pc

        owner_id = await get_member_id_by_phone(conn, owner_phone)
        partner_id = (
            await get_member_id_by_phone(conn, accountability_partner_phone) if accountability_partner_phone else None
        )

        current_state = "TODO" if status == "ACTIVE" else "ARCHIVED"

        verification = "partner" if partner_id else "none"

        await conn.execute(
            """INSERT OR IGNORE INTO tasks
               (id, created, updated, title, owner_id, schedule_cron,
                 deadline, scope, verification, accountability_partner_id,
                 current_state, module)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'personal', ?, ?, ?, 'task')""",
            (old_id, created, updated, title, owner_id, recurrence, due_date, verification, partner_id, current_state),
        )
        migrated += 1

    await conn.commit()
    logger.info("Migrated %d personal_chores to tasks (scope='personal', verification='partner')", migrated)
    return migrated


async def migrate_logs_to_task_logs(conn: aiosqlite.Connection) -> int:
    """Migrate logs table to task_logs table."""
    if not await table_exists(conn, "logs"):
        logger.info("Old 'logs' table does not exist, skipping migration")
        return 0

    cursor = await conn.execute(
        """SELECT id, created, updated, chore_id, user_id, action, notes,
                  timestamp, original_assignee_id, actual_completer_id, is_swap
           FROM logs"""
    )
    logs = await cursor.fetchall()

    migrated = 0
    for log in logs:
        (
            old_id,
            created,
            updated,
            chore_id,
            user_id,
            action,
            notes,
            timestamp,
            original_assignee_id,
            actual_completer_id,
            is_swap,
        ) = log

        await conn.execute(
            """INSERT OR IGNORE INTO task_logs
                (id, created, updated, task_id, user_id, action, notes,
                 timestamp, original_assignee_id, actual_completer_id, is_swap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                old_id,
                created,
                updated,
                chore_id,
                user_id,
                action,
                notes,
                timestamp,
                original_assignee_id,
                actual_completer_id,
                is_swap,
            ),
        )
        migrated += 1

    await conn.commit()
    logger.info("Migrated %d logs to task_logs", migrated)
    return migrated


async def migrate_personal_chore_logs_to_task_logs(conn: aiosqlite.Connection) -> int:
    """Migrate personal_chore_logs table to task_logs table."""
    if not await table_exists(conn, "personal_chore_logs"):
        logger.info("Old 'personal_chore_logs' table does not exist, skipping migration")
        return 0

    cursor = await conn.execute(
        """SELECT id, created, updated, personal_chore_id, owner_phone,
                  completed_at, verification_status, accountability_partner_phone,
                  partner_feedback, notes
           FROM personal_chore_logs"""
    )
    personal_chore_logs = await cursor.fetchall()

    migrated = 0
    for pcl in personal_chore_logs:
        (
            old_id,
            created,
            updated,
            personal_chore_id,
            owner_phone,
            completed_at,
            verification_status,
            accountability_partner_phone,
            partner_feedback,
            notes,
        ) = pcl

        owner_id = await get_member_id_by_phone(conn, owner_phone)
        verifier_id = (
            await get_member_id_by_phone(conn, accountability_partner_phone) if accountability_partner_phone else None
        )

        await conn.execute(
            """INSERT OR IGNORE INTO task_logs
                (id, created, updated, task_id, user_id, action, notes,
                 timestamp, verification_status, verifier_id, verifier_feedback)
                VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)""",
            (
                old_id,
                created,
                updated,
                personal_chore_id,
                owner_id,
                notes,
                completed_at,
                verification_status,
                verifier_id,
                partner_feedback,
            ),
        )
        migrated += 1

    await conn.commit()
    logger.info("Migrated %d personal_chore_logs to task_logs", migrated)
    return migrated


async def update_workflow_types(conn: aiosqlite.Connection) -> int:
    """Update workflow type values: chore_verification and personal_verification -> task_verification."""
    migrated = 0

    for old_type in OLD_WORKFLOW_TYPES:
        cursor = await conn.execute("SELECT COUNT(*) FROM workflows WHERE type=?", (old_type,))
        count_row = await cursor.fetchone()
        count = count_row[0] if count_row else 0

        if count > 0:
            await conn.execute(
                "UPDATE workflows SET type='task_verification' WHERE type=?",
                (old_type,),
            )
            migrated += count
            logger.info(
                "Updated %d workflows from type '%s' to 'task_verification'",
                count,
                old_type,
            )

    await conn.commit()
    return migrated


async def add_schema_version(conn: aiosqlite.Connection) -> None:
    """Add schema_version column to house_config if it doesn't exist."""
    if not await table_exists(conn, "house_config"):
        logger.warning("house_config table does not exist, skipping schema_version addition")
        return

    cursor = await conn.execute("PRAGMA table_info(house_config)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]

    if "schema_version" not in column_names:
        await conn.execute("ALTER TABLE house_config ADD COLUMN schema_version TEXT")
        await conn.execute("UPDATE house_config SET schema_version='v2'")
        await conn.commit()
        logger.info("Added schema_version column to house_config and set to 'v2'")
    else:
        await conn.execute("UPDATE house_config SET schema_version='v2' WHERE schema_version IS NULL")
        await conn.commit()
        logger.info("Updated schema_version in house_config to 'v2'")


async def drop_old_tables(conn: aiosqlite.Connection, *, confirm: bool = False) -> None:
    """Drop old tables after verification step (requires confirmation)."""
    if not confirm:
        logger.info("Skipping table drop (use --drop-old-tables to confirm)")
        return

    for table in OLD_TABLES:
        if await table_exists(conn, table):
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
            logger.info("Dropped old table: %s", table)

    await conn.commit()
    logger.info("Dropped all old tables")


async def run_migration(*, db_path: Path, should_drop_old_tables: bool = False) -> dict[str, int]:
    """Run the complete migration from v1 to v2."""
    logger.info("Starting migration v1 to v2 on database: %s", db_path)

    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")

        backup_path = await create_backup(db_path=db_path)

        results: dict[str, int] = {}

        results["chores_migrated"] = await migrate_chores_to_tasks(conn)
        results["personal_chores_migrated"] = await migrate_personal_chores_to_tasks(conn)
        results["logs_migrated"] = await migrate_logs_to_task_logs(conn)
        results["personal_chore_logs_migrated"] = await migrate_personal_chore_logs_to_task_logs(conn)
        results["workflows_updated"] = await update_workflow_types(conn)

        await add_schema_version(conn)

        await drop_old_tables(conn, confirm=should_drop_old_tables)

        total_migrated = sum(results.values())
        logger.info("Migration complete. Total records migrated: %d", total_migrated)
        logger.info("Backup saved at: %s", backup_path)

        return results


async def verify_migration(*, db_path: Path) -> bool:
    """Verify that migration was successful by checking data integrity."""
    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")

        tasks_count_row = await (await conn.execute("SELECT COUNT(*) FROM tasks")).fetchone()
        task_logs_count_row = await (await conn.execute("SELECT COUNT(*) FROM task_logs")).fetchone()
        house_config_cursor = await conn.execute("SELECT schema_version FROM house_config LIMIT 1")
        house_config_row = await house_config_cursor.fetchone()

        tasks_count = tasks_count_row[0] if tasks_count_row else 0
        task_logs_count = task_logs_count_row[0] if task_logs_count_row else 0
        schema_version = house_config_row[0] if house_config_row else None

        logger.info("Verification:")
        logger.info("  - Tasks: %d", tasks_count)
        logger.info("  - Task logs: %d", task_logs_count)
        logger.info("  - Schema version: %s", schema_version or "not set")

        return schema_version == "v2"


def main() -> None:
    """Main entry point for the migration script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Migrate database from v1 to v2 schema")
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to database file (default: uses settings.sqlite_db_path)",
    )
    parser.add_argument(
        "--drop-old-tables",
        action="store_true",
        help="Drop old tables after migration (confirmation required)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify migration status without running migration",
    )

    args = parser.parse_args()

    db_path = Path(args.db_path).resolve() if args.db_path else Path(settings.sqlite_db_path).resolve()

    if args.verify_only:
        success = asyncio.run(verify_migration(db_path=db_path))
        if success:
            logger.info("✓ Migration verified successfully")
        else:
            logger.error("✗ Migration verification failed")
            sys.exit(1)
    else:
        results = asyncio.run(run_migration(db_path=db_path, should_drop_old_tables=args.drop_old_tables))
        logger.info("Migration Summary:")
        for key, value in results.items():
            logger.info("  %s: %s", key, value)
        logger.info(
            "Backup created at: %s",
            db_path.parent / f"{db_path.stem}_backup_*{db_path.suffix}",
        )


if __name__ == "__main__":
    main()
