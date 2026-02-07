"""House configuration service."""

import logging

from pydantic import BaseModel

from src.core import db_client
from src.core.config import settings


logger = logging.getLogger(__name__)


class HouseConfig(BaseModel):
    """House configuration data transfer object."""

    name: str
    group_chat_id: str | None = None
    activation_key: str | None = None


async def get_house_config() -> HouseConfig:
    """Get house configuration from database or fallback to environment variables."""
    config = await db_client.get_first_record(collection="house_config", filter_query="")

    if config:
        return HouseConfig(
            name=config["name"],
            group_chat_id=config.get("group_chat_id"),
            activation_key=config.get("activation_key"),
        )

    house_name = settings.house_name or "the house"

    logger.warning("house_config_not_found_using_env_fallback", extra={"house_name": house_name})

    return HouseConfig(name=house_name)


async def ensure_singleton_config() -> HouseConfig | None:
    """Ensure only one house_config record exists, deleting duplicates if found."""
    try:
        all_configs = await db_client.list_records(collection="house_config", per_page=100)

        if len(all_configs) <= 1:
            if all_configs:
                c = all_configs[0]
                return HouseConfig(
                    name=c["name"],
                    group_chat_id=c.get("group_chat_id"),
                    activation_key=c.get("activation_key"),
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
            group_chat_id=first_config.get("group_chat_id"),
            activation_key=first_config.get("activation_key"),
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


async def set_activation_key(key: str) -> bool:
    """Set the activation key in house configuration.

    Args:
        key: The activation key (e.g., "tiger-mountain-gold")

    Returns:
        True if successfully set, False otherwise
    """
    try:
        config = await db_client.get_first_record(collection="house_config", filter_query="")

        if not config:
            logger.warning("Cannot set activation_key - no house_config exists")
            return False

        await db_client.update_record(
            collection="house_config",
            record_id=config["id"],
            data={"activation_key": key},
        )
        logger.info("activation_key_set")
        return True
    except Exception as e:
        logger.error("activation_key_set_failed", extra={"error": str(e)})
        return False


async def clear_activation_key() -> bool:
    """Clear the activation key from house configuration.

    Returns:
        True if successfully cleared, False otherwise
    """
    try:
        config = await db_client.get_first_record(collection="house_config", filter_query="")

        if not config:
            logger.warning("Cannot clear activation_key - no house_config exists")
            return False

        await db_client.update_record(
            collection="house_config",
            record_id=config["id"],
            data={"activation_key": None},
        )
        logger.info("activation_key_cleared")
        return True
    except Exception as e:
        logger.error("activation_key_clear_failed", extra={"error": str(e)})
        return False


async def seed_from_env_vars() -> None:
    """Seed house_config collection from environment variables if empty."""
    try:
        config = await db_client.get_first_record(collection="house_config", filter_query="")

        if config:
            logger.info("house_config_already_exists", extra={"name": config["name"]})
            return

        if not settings.house_name:
            logger.info("house_config_not_seeded_missing_env_vars")
            return

        data = {
            "name": settings.house_name,
        }

        await db_client.create_record(collection="house_config", data=data)
        logger.info("house_config_seeded_from_env_vars", extra={"name": data["name"]})
    except Exception as e:
        logger.error("house_config_seed_failed", extra={"error": str(e)})
