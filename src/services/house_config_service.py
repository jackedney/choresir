"""House configuration service."""

import logging
import secrets
from typing import Any

from src.core import db_client
from src.core.config import settings


logger = logging.getLogger(__name__)


async def get_house_config() -> dict[str, Any]:
    """Get house configuration from database or fallback to environment variables.

    Returns:
        Dictionary with keys: name, password, code (from DB or env vars)

    Note:
        If no config exists in database, falls back to environment variables.
        This ensures backward compatibility during initial deployment.
    """
    config = await db_client.get_first_record(collection="house_config", filter_query="")

    if config:
        return {"name": config["name"], "password": config["password"], "code": config["code"]}

    house_name = settings.house_name or "the house"
    house_code = settings.house_code or ""
    house_password = settings.house_password or ""

    logger.warning("house_config_not_found_using_env_fallback", extra={"house_name": house_name})

    return {"name": house_name, "password": house_password, "code": house_code}


async def validate_house_credentials(*, house_code: str, password: str) -> bool:
    """Validate house code and password against stored configuration.

    Uses constant-time comparison for security (prevents timing attacks).

    Args:
        house_code: House code to validate
        password: House password to validate

    Returns:
        True if both code and password are correct, False otherwise

    Note:
        Falls back to environment variables if no config exists in database.
    """
    config = await get_house_config()

    if not config["code"]:
        return False
    if not config["password"]:
        return False

    house_code_valid = secrets.compare_digest(house_code, config["code"])
    password_valid = secrets.compare_digest(password, config["password"])

    return house_code_valid and password_valid


async def validate_house_password(*, password: str) -> bool:
    """Validate house password against stored configuration.

    Uses constant-time comparison for security (prevents timing attacks).

    Args:
        password: House password to validate

    Returns:
        True if password is correct, False otherwise

    Note:
        Falls back to environment variables if no config exists in database.
    """
    config = await get_house_config()

    if not config["password"]:
        return False

    return secrets.compare_digest(password, config["password"])


async def ensure_singleton_config() -> dict[str, Any] | None:
    """Ensure only one house_config record exists in the database.

    If multiple records exist, keeps the first one and deletes the rest.

    Returns:
        The single house_config record if it exists, None otherwise

    Note:
        This is a safety measure to maintain singleton behavior.
        The admin interface already enforces this, but this provides
        a database-level safeguard.
    """
    try:
        all_configs = await db_client.list_records(collection="house_config", per_page=100)

        if len(all_configs) <= 1:
            return all_configs[0] if all_configs else None

        logger.warning(
            "house_config_multiple_records_found",
            extra={"count": len(all_configs)},
        )

        first_config = all_configs[0]

        for config in all_configs[1:]:
            await db_client.delete_record(collection="house_config", record_id=config["id"])
            logger.info("house_config_duplicate_deleted", extra={"id": config["id"]})

        return first_config
    except Exception as e:
        logger.error("house_config_singleton_check_failed", extra={"error": str(e)})
        return None


async def seed_from_env_vars() -> None:
    """Seed house_config collection with values from environment variables.

    Only creates a record if:
    - Collection is empty AND
    - All required environment variables are set (HOUSE_NAME, HOUSE_PASSWORD, HOUSE_CODE)

    Returns:
        None

    Note:
        This is safe to call idempotently. It will not overwrite existing data.
    """
    try:
        config = await db_client.get_first_record(collection="house_config", filter_query="")

        if config:
            logger.info("house_config_already_exists", extra={"name": config["name"]})
            return

        if not settings.house_name or not settings.house_code or not settings.house_password:
            logger.info("house_config_not_seeded_missing_env_vars")
            return

        data = {
            "name": settings.house_name,
            "password": settings.house_password,
            "code": settings.house_code,
        }

        await db_client.create_record(collection="house_config", data=data)
        logger.info("house_config_seeded_from_env_vars", extra={"name": data["name"]})
    except Exception as e:
        logger.error("house_config_seed_failed", extra={"error": str(e)})
