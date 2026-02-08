"""Admin interface router for web UI."""

import logging
import os
import secrets

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.core.config import constants, settings
from src.core.db_client import (
    create_record,
    delete_record,
    get_first_record,
    list_records,
    sanitize_param,
    update_record,
)
from src.domain.create_models import HouseConfigCreate
from src.domain.update_models import MemberUpdate
from src.services.activation_key_service import generate_activation_key
from src.services.house_config_service import (
    get_house_config as get_house_config_from_service,
    set_activation_key,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-session")
csrf_serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-csrf")


def generate_csrf_token() -> str:
    """Generate a secure CSRF token."""
    return secrets.token_hex(32)


def set_csrf_cookie(response: Response, csrf_token: str) -> None:
    """Set the CSRF cookie on a response."""
    signed_token = csrf_serializer.dumps(csrf_token)
    response.set_cookie(
        key="csrf_token",
        value=signed_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=3600,
    )


def validate_csrf_token(request: Request, token: str | None) -> bool:
    """Validate CSRF token from request against signed cookie value."""
    if not token:
        return False

    expected_token = request.cookies.get("csrf_token")
    if not expected_token:
        return False

    try:
        loaded_token = csrf_serializer.loads(expected_token, max_age=3600)
        return secrets.compare_digest(loaded_token, token)
    except (BadSignature, SignatureExpired):
        return False


async def require_auth(request: Request) -> None:
    """Check for valid admin session and redirect to login if invalid."""
    session_token = request.cookies.get("admin_session")

    if not session_token:
        logger.warning("admin_auth_missing_cookie", extra={"path": request.url.path})
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )

    try:
        session_data = serializer.loads(session_token, max_age=86400)
        if not session_data.get("authenticated"):
            logger.warning("admin_auth_invalid_session", extra={"path": request.url.path})
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": "/admin/login"},
            )
    except (BadSignature, SignatureExpired) as err:
        logger.warning("admin_auth_tampered_or_expired", extra={"path": request.url.path})
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        ) from err


@router.get("/")
async def get_admin_dashboard(request: Request, _auth: None = Depends(require_auth)) -> Response:
    """Render the admin dashboard with member statistics."""
    config = await get_house_config_from_service()
    house_name = config.name

    users = await list_records(collection="members", per_page=1000)

    total_members = len(users)
    active_members = sum(1 for user in users if user.get("status") == "active")
    pending_members = sum(1 for user in users if user.get("status") == "pending_name")

    return templates.TemplateResponse(
        request,
        name="admin/dashboard.html",
        context={
            "house_name": house_name,
            "total_members": total_members,
            "active_members": active_members,
            "pending_members": pending_members,
        },
    )


@router.get("/login")
async def get_login(request: Request) -> Response:
    """Render the admin login form with CSRF token."""
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse(request, name="admin/login.html", context={"csrf_token": csrf_token})
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/login")
async def post_login(
    *,
    request: Request,
    response: Response,
    password: str = Form(...),
    csrf_token: str | None = Form(None),
) -> Response:
    """Process admin login and redirect to dashboard on success."""
    if not validate_csrf_token(request, csrf_token):
        logger.warning("admin_login_invalid_csrf")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )

    expected_password = settings.admin_password

    if not expected_password:
        logger.error("admin_login_missing_password")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin password not configured",
        )

    if secrets.compare_digest(password, expected_password):
        session_token = serializer.dumps({"authenticated": True})

        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="admin_session",
            value=session_token,
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            max_age=86400,
        )
        response.delete_cookie(key="csrf_token", httponly=True, samesite="strict")
        return response

    error = "Invalid password"
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse(
        request,
        name="admin/login.html",
        context={"error": error, "csrf_token": csrf_token},
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/logout")
async def logout() -> Response:
    """Clear admin session and redirect to login."""
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="admin_session", httponly=True, samesite="strict")
    logger.info("admin_logout_success")
    return response


@router.get("/house")
async def get_house_config(request: Request, _auth: None = Depends(require_auth)) -> Response:
    """Render house configuration form."""
    config = await get_first_record(collection="house_config", filter_query="")
    success_message = request.cookies.get("flash_success")

    if config:
        house_name = config.get("name") or ""
    else:
        default_config = await get_house_config_from_service()
        house_name = default_config.name

    return templates.TemplateResponse(
        request,
        name="admin/house.html",
        context={
            "house_name": house_name,
            "success_message": success_message,
        },
    )


@router.post("/house")
async def post_house_config(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    name: str = Form(...),
) -> Response:
    """Update house configuration and redirect on success."""
    errors = []

    if len(name) < 1 or len(name) > 50:
        errors.append("Name must be between 1 and 50 characters")

    if errors:
        return templates.TemplateResponse(
            request,
            name="admin/house.html",
            context={
                "errors": errors,
                "house_name": name,
                "success_message": None,
            },
        )

    house_config = HouseConfigCreate(name=name)

    config = await get_first_record(collection="house_config", filter_query="")
    if config:
        await update_record(
            collection="house_config", record_id=config["id"], data=house_config.model_dump(exclude_none=True)
        )
        logger.info("house_config_updated", extra={"name": name})
        message = "House configuration updated successfully"
    else:
        await create_record(collection="house_config", data=house_config.model_dump())
        logger.info("house_config_created", extra={"name": name})
        message = "House configuration created successfully"

    response = RedirectResponse(url="/admin/house", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("flash_success", message, max_age=5)
    return response


def is_htmx_request(request: Request) -> bool:
    """Check if the request is from HTMX."""
    return request.headers.get("HX-Request") == "true"


@router.get("/members")
async def get_members(request: Request, _auth: None = Depends(require_auth)) -> Response:
    """Render member list with status and role badges."""
    users = await list_records(collection="members", per_page=1000)
    success_message = request.cookies.get("flash_success")

    return templates.TemplateResponse(
        request, name="admin/members.html", context={"members": users, "success_message": success_message}
    )


@router.get("/members/{phone}/row")
async def get_member_row(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
) -> Response:
    """Get a single member row fragment for HTMX updates."""
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return templates.TemplateResponse(
        request,
        name="admin/member_row.html",
        context={"member": user},
    )


@router.get("/members/{phone}/edit")
async def get_edit_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
) -> Response:
    """Render edit member form (inline for HTMX, full page otherwise)."""
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    csrf_token = generate_csrf_token()
    template_name = "admin/edit_member_inline.html" if is_htmx_request(request) else "admin/edit_member.html"
    response = templates.TemplateResponse(
        request,
        name=template_name,
        context={"user": user, "csrf_token": csrf_token},
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/members/{phone}/edit")
async def post_edit_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
    name: str = Form(...),
    role: str = Form(...),
    csrf_token: str | None = Form(None),
) -> Response:
    """Process edit member form and update user record."""
    if not validate_csrf_token(request, csrf_token):
        logger.warning("admin_edit_member_invalid_csrf")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )

    errors = []

    # Validate name
    if not name or len(name.strip()) < 1:
        errors.append("Name cannot be empty")
    elif len(name) > 50:
        errors.append("Name must be 50 characters or less")
    elif not all(c.isalpha() or c.isspace() or c in "-'" for c in name):
        errors.append("Name can only contain letters, spaces, hyphens, and apostrophes")

    # Validate role
    if role not in ("admin", "member"):
        errors.append("Invalid role")

    if errors:
        # Get user for form repopulation
        user = await get_first_record(
            collection="members",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        new_csrf_token = generate_csrf_token()
        template_name = "admin/edit_member_inline.html" if is_htmx_request(request) else "admin/edit_member.html"
        response = templates.TemplateResponse(
            request,
            name=template_name,
            context={"errors": errors, "user": user, "name": name, "role": role, "csrf_token": new_csrf_token},
        )
        set_csrf_cookie(response, new_csrf_token)
        return response

    # Find user by phone
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update user record using DTO
    member_update = MemberUpdate(name=name.strip(), role=role)
    await update_record(
        collection="members",
        record_id=user["id"],
        data=member_update.model_dump(),
    )
    logger.info("member_updated", extra={"phone": phone, "name": name, "role": role})

    # Re-fetch user data to get updated values for HTMX response
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if is_htmx_request(request):
        return templates.TemplateResponse(
            request,
            name="admin/member_row.html",
            context={"member": user},
        )

    response = RedirectResponse(url="/admin/members", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("flash_success", "Member updated successfully", max_age=5)
    return response


@router.get("/members/{phone}/remove")
async def get_remove_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
) -> Response:
    """Render remove member confirmation page."""
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    csrf_token = generate_csrf_token()
    template_name = "admin/remove_member_inline.html" if is_htmx_request(request) else "admin/remove_member.html"
    response = templates.TemplateResponse(
        request,
        name=template_name,
        context={"user": user, "csrf_token": csrf_token},
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/members/{phone}/remove")
async def post_remove_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
    csrf_token: str | None = Form(None),
) -> Response:
    """Process remove member form and delete the user."""
    if not validate_csrf_token(request, csrf_token):
        logger.warning("admin_remove_member_invalid_csrf")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )

    # Find user by phone
    user = await get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent removing admins
    if user.get("role") == "admin":
        new_csrf_token = generate_csrf_token()
        if is_htmx_request(request):
            response = templates.TemplateResponse(
                request,
                name="admin/remove_member_inline.html",
                context={"errors": ["Cannot remove an admin"], "user": user, "csrf_token": new_csrf_token},
            )
        else:
            response = templates.TemplateResponse(
                request,
                name="admin/remove_member.html",
                context={"errors": ["Cannot remove an admin"], "user": user, "csrf_token": new_csrf_token},
            )
        set_csrf_cookie(response, new_csrf_token)
        return response

    # Delete the user record
    await delete_record(collection="members", record_id=user["id"])
    logger.info("removed_member", extra={"phone": phone})

    if is_htmx_request(request):
        # Return empty response to remove the row from the table
        return Response(content="", status_code=status.HTTP_200_OK)

    response = RedirectResponse(url="/admin/members", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("flash_success", "Member removed", max_age=5)
    return response


# =============================================================================
# WhatsApp Setup Routes
# =============================================================================


def _get_waha_headers() -> dict[str, str]:
    """Get headers for WAHA API requests."""
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key
    return headers


@router.get("/whatsapp")
async def get_whatsapp_setup(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
) -> Response:
    """Render WhatsApp setup page."""
    return templates.TemplateResponse(request, name="admin/whatsapp.html")


@router.get("/whatsapp/status")
async def get_whatsapp_status(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Get WhatsApp session status from WAHA."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.waha_base_url}/api/sessions/default",
                headers=_get_waha_headers(),
            )

            if response.status_code == 404:
                return {"status": "NOT_FOUND", "phone": None, "webhook_configured": False}

            response.raise_for_status()
            data = response.json()

            phone = None
            if data.get("me"):
                # Extract phone from WAHA format (e.g., "447871681224@c.us" -> "+447871681224")
                me_id = data["me"].get("id", "")
                if "@" in me_id:
                    phone = "+" + me_id.split("@")[0]

            # Check if webhook is configured
            config = data.get("config") or {}
            webhooks = config.get("webhooks") or []
            webhook_configured = len(webhooks) > 0

            return {
                "status": data.get("status", "UNKNOWN"),
                "phone": phone,
                "webhook_configured": webhook_configured,
            }
    except httpx.HTTPStatusError as e:
        logger.error("waha_status_error", extra={"error": str(e), "status_code": e.response.status_code})
        return {"status": "ERROR", "phone": None, "webhook_configured": False, "error": str(e)}
    except httpx.RequestError as e:
        logger.error("waha_connection_error", extra={"error": str(e)})
        return {"status": "ERROR", "phone": None, "webhook_configured": False, "error": str(e)}


@router.get("/whatsapp/qr")
async def get_whatsapp_qr(
    *,
    _auth: None = Depends(require_auth),
) -> Response:
    """Get QR code image from WAHA."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.waha_base_url}/api/default/auth/qr",
                headers=_get_waha_headers(),
            )
            response.raise_for_status()

            return Response(
                content=response.content,
                media_type="image/png",
            )
    except httpx.RequestError as e:
        logger.error("waha_qr_fetch_error", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch QR code from WAHA",
        ) from e


@router.post("/whatsapp/start")
async def start_whatsapp_session(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Start a new WhatsApp session in WAHA."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.waha_base_url}/api/sessions/default/start",
                headers=_get_waha_headers(),
            )
            response.raise_for_status()
            return {"success": True}
    except httpx.RequestError as e:
        logger.error("waha_start_session_error", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start WhatsApp session",
        ) from e


def _get_webhook_url() -> str:
    """Get the webhook URL for WAHA to call back.

    Uses WHATSAPP_HOOK_URL env var if set, otherwise constructs from request context.
    For Docker, this should be http://host.docker.internal:PORT/webhook
    """
    # Check for explicit env var first
    hook_url = os.environ.get("WHATSAPP_HOOK_URL")
    if hook_url:
        return hook_url

    # Default for local Docker setup
    return "http://host.docker.internal:8001/webhook"


@router.post("/whatsapp/configure-webhook")
async def configure_whatsapp_webhook(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Configure webhook on the WAHA session."""
    webhook_url = _get_webhook_url()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{settings.waha_base_url}/api/sessions/default",
                headers=_get_waha_headers(),
                json={
                    "config": {
                        "webhooks": [
                            {
                                "url": webhook_url,
                                # Use message.any to include self-sent messages (for testing)
                                "events": ["message.any"],
                            }
                        ]
                    }
                },
            )
            response.raise_for_status()
            logger.info("waha_webhook_configured", extra={"webhook_url": webhook_url})
            return {"success": True, "webhook_url": webhook_url}
    except httpx.HTTPStatusError as e:
        logger.error("waha_configure_webhook_error", extra={"error": str(e), "status": e.response.status_code})
        return {"success": False, "error": f"WAHA returned {e.response.status_code}"}
    except httpx.RequestError as e:
        logger.error("waha_configure_webhook_error", extra={"error": str(e)})
        return {"success": False, "error": str(e)}


@router.get("/whatsapp/activation-status")
async def get_activation_status(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Get the current activation key and group configuration status."""
    config = await get_first_record(collection="house_config", filter_query="")
    if not config:
        return {"activation_key": None, "group_chat_id": None, "has_config": False}

    return {
        "activation_key": config.get("activation_key"),
        "group_chat_id": config.get("group_chat_id"),
        "has_config": True,
    }


@router.post("/whatsapp/generate-activation-key")
async def post_generate_activation_key(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Generate a new activation key for group activation."""
    # Check if house config exists
    config = await get_first_record(collection="house_config", filter_query="")
    if not config:
        return {"success": False, "error": "House configuration not found. Please configure house settings first."}

    # Check if group is already configured
    if config.get("group_chat_id"):
        return {"success": False, "error": "A group is already configured. Clear it first to generate a new key."}

    # Generate and save activation key
    key = generate_activation_key()
    success = await set_activation_key(key)

    if success:
        logger.info("activation_key_generated")
        return {"success": True, "activation_key": key}
    return {"success": False, "error": "Failed to save activation key"}


@router.post("/whatsapp/clear-group")
async def post_clear_group(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Clear the current group configuration."""
    config = await get_first_record(collection="house_config", filter_query="")
    if not config:
        return {"success": False, "error": "House configuration not found."}

    await update_record(
        collection="house_config",
        record_id=config["id"],
        data={"group_chat_id": None, "activation_key": None},
    )
    logger.info("group_configuration_cleared")
    return {"success": True, "message": "Group configuration cleared"}
