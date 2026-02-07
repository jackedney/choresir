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


HTTP_NOT_FOUND = 404


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

    return await _fetch_phone_from_lid(lid=lid, session=session)


async def _fetch_phone_from_lid(*, lid: str, session: str) -> str | None:
    """Internal: Fetch phone number from WAHA LID endpoint."""
    encoded_lid = lid.replace("@", "%40")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.waha_base_url}/api/{session}/lids/{encoded_lid}",
                headers=_get_waha_headers(),
            )

            if response.status_code == HTTP_NOT_FOUND:
                logger.debug("LID not found in WAHA", extra={"lid": lid})
                return None

            response.raise_for_status()
            return _parse_lid_response(lid=lid, data=response.json())

    except httpx.HTTPStatusError as e:
        logger.error("WAHA LID resolution HTTP error", extra={"lid": lid, "status": e.response.status_code})
    except httpx.RequestError as e:
        logger.error("WAHA LID resolution connection error", extra={"lid": lid, "error": str(e)})
    except Exception as e:
        logger.error("WAHA LID resolution unexpected error", extra={"lid": lid, "error": str(e)})
    return None


def _parse_lid_response(*, lid: str, data: dict) -> str | None:
    """Parse WAHA LID response and extract phone number."""
    pn = data.get("pn")
    if not pn:
        logger.debug("LID resolved but no phone number", extra={"lid": lid, "response": data})
        return None

    phone = pn.replace("@c.us", "").replace("@s.whatsapp.net", "")

    if not re.match(r"^\d{1,15}$", phone):
        logger.warning("Invalid phone format from LID resolution", extra={"lid": lid, "pn": pn})
        return None

    logger.info("Resolved LID to phone", extra={"lid": lid, "phone": f"+{phone}"})
    return f"+{phone}"
