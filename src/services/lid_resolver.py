"""Service to resolve WhatsApp @lid (Linked ID) to phone numbers via WAHA API."""

import logging
import re

import httpx

from src.core.config import settings


logger = logging.getLogger(__name__)


def _get_waha_headers() -> dict[str, str]:
    """Get headers for WAHA API requests."""
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key
    return headers


async def resolve_lid_to_phone(lid: str, session: str = "default") -> str | None:
    """Resolve a WhatsApp @lid to a phone number using WAHA API.

    WhatsApp uses Linked IDs (@lid) to hide phone numbers in some contexts.
    This calls WAHA's /api/{session}/lids/{lid} endpoint to get the real phone.

    Args:
        lid: The @lid identifier (e.g., "118777370906868@lid")
        session: WAHA session name (default: "default")

    Returns:
        Phone number in E.164 format (e.g., "+447871681224") or None if not found
    """
    if not lid or "@lid" not in lid:
        return None

    # URL-encode the @ symbol
    encoded_lid = lid.replace("@", "%40")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.waha_base_url}/api/{session}/lids/{encoded_lid}",
                headers=_get_waha_headers(),
            )

            if response.status_code == 404:
                logger.debug("LID not found in WAHA", extra={"lid": lid})
                return None

            response.raise_for_status()
            data = response.json()

            # Response format: {"lid": "123@lid", "pn": "447871681224@c.us"}
            pn = data.get("pn")
            if not pn:
                logger.debug("LID resolved but no phone number", extra={"lid": lid, "response": data})
                return None

            # Extract phone number from @c.us format
            phone = pn.replace("@c.us", "").replace("@s.whatsapp.net", "")

            # Validate it looks like a phone number
            if not re.match(r"^\d{1,15}$", phone):
                logger.warning("Invalid phone format from LID resolution", extra={"lid": lid, "pn": pn})
                return None

            logger.info("Resolved LID to phone", extra={"lid": lid, "phone": f"+{phone}"})
            return f"+{phone}"

    except httpx.HTTPStatusError as e:
        logger.error("WAHA LID resolution HTTP error", extra={"lid": lid, "status": e.response.status_code})
        return None
    except httpx.RequestError as e:
        logger.error("WAHA LID resolution connection error", extra={"lid": lid, "error": str(e)})
        return None
    except Exception as e:
        logger.error("WAHA LID resolution unexpected error", extra={"lid": lid, "error": str(e)})
        return None
