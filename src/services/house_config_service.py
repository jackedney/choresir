"""House configuration service."""

import logging
import secrets

from pydantic import BaseModel

from src.core import db_client
from src.core.config import settings


logger = logging.getLogger(__name__)


class HouseConfig(BaseModel):
    """House configuration data transfer object."""

    name: str
    password: str
    code: str
    group_chat_id: str | None = None


async def get_house_config() -> HouseConfig:
    """Get house configuration from database or fallback to environment variables."""
    config = await db_client.get_first_record(collection="house_config", filter_query="")

    if config:
        return HouseConfig(
            name=config["name"],
            password=config["password"],
            code=config["code"],
            group_chat_id=config.get("group_chat_id"),
        )

    house_name = settings.house_name or "the house"
    house_code = settings.house_code or ""
    house_password = settings.house_password or ""

    logger.warning("house_config_not_found_using_env_fallback", extra={"house_name": house_name})

    return HouseConfig(name=house_name, password=house_password, code=house_code)


async def validate_house_credentials(*, house_code: str, password: str) -> bool:
    """Validate house code and password against stored configuration."""
    config = await get_house_config()

    if not config.code or not config.password:
        return False

    house_code_valid = secrets.compare_digest(house_code, config.code)
    password_valid = secrets.compare_digest(password, config.password)

    return house_code_valid and password_valid


async def validate_house_password(*, password: str) -> bool:
    """Validate house password against stored configuration."""
    config = await get_house_config()

    if not config.password:
        return False

    return secrets.compare_digest(password, config.password)


async def ensure_singleton_config() -> HouseConfig | None:
    """Ensure only one house_config record exists, deleting duplicates if found."""
    try:
        all_configs = await db_client.list_records(collection="house_config", per_page=100)

        if len(all_configs) <= 1:
            if all_configs:
                c = all_configs[0]
                return HouseConfig(
                    name=c["name"],
                    password=c["password"],
                    code=c["code"],
                    group_chat_id=c.get("group_chat_id"),
                )
            return None

        logger.warning(
            "house_config_multiple_records_found",
            extra={"count": len(all_configs)},
        )

        first_config = all_configs[0]

        for config in all_configs[1:]:
            await db_client.delete_record(collection="house_config", record_id=config["id"])
            logger.info("house_config_duplicate_deleted", extra={"id": config["id"]})

        return HouseConfig(
            name=first_config["name"],
            password=first_config["password"],
            code=first_config["code"],
            group_chat_id=first_config.get("group_chat_id"),
        )
    except Exception as e:
        logger.error("house_config_singleton_check_failed", extra={"error": str(e)})
        return None


async def set_group_chat_id(group_id: str) -> bool:
    """Set the group chat ID in house configuration.

    Args:
        group_id: The WhatsApp group ID (e.g., 120363400136168625@g.us)

    Returns:
        True if successfully set, False otherwise
    """
    try:
        config = await db_client.get_first_record(collection="house_config", filter_query="")

        if not config:
            logger.warning("Cannot set group_chat_id - no house_config exists")
            return False

        await db_client.update_record(
            collection="house_config",
            record_id=config["id"],
            data={"group_chat_id": group_id},
        )
        logger.info("group_chat_id_set", extra={"group_id": group_id})
        return True
    except Exception as e:
        logger.error("group_chat_id_set_failed", extra={"error": str(e), "group_id": group_id})
        return False


async def seed_from_env_vars() -> None:
    """Seed house_config collection from environment variables if empty."""
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
