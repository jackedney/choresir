"""Admin interface router for web UI."""

import logging
import secrets
from datetime import UTC, datetime

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
from src.domain.create_models import HouseConfigCreate, InviteCreate, UserCreate
from src.domain.update_models import MemberUpdate
from src.domain.user import UserRole, UserStatus
from src.interface.whatsapp_sender import send_text_message
from src.services.house_config_service import get_house_config as get_house_config_from_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-session")
csrf_serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-csrf")

# Placeholder string for obscured text display
MASKED_TEXT_PLACEHOLDER = "********"


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

    users = await list_records(collection="users", per_page=1000)

    total_members = len(users)
    active_members = sum(1 for user in users if user.get("status") == "active")
    pending_members = sum(1 for user in users if user.get("status") == "pending")

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
        house_code = config.get("code") or ""
        house_password = MASKED_TEXT_PLACEHOLDER
    else:
        default_config = await get_house_config_from_service()
        house_name = default_config.name
        house_code = default_config.code
        house_password = ""

    return templates.TemplateResponse(
        request,
        name="admin/house.html",
        context={
            "house_name": house_name,
            "house_code": house_code,
            "house_password": house_password,
            "success_message": success_message,
        },
    )


@router.post("/house")
async def post_house_config(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    name: str = Form(...),
    code: str = Form(...),
    password: str = Form(""),
) -> Response:
    """Update house configuration and redirect on success."""
    errors = []

    if len(name) < 1 or len(name) > 50:
        errors.append("Name must be between 1 and 50 characters")

    if len(code) < 4:
        errors.append("Code must be at least 4 characters")

    # Check if we're updating (config exists) and password is the placeholder or empty
    config = await get_first_record(collection="house_config", filter_query="")
    password_is_placeholder = password in (MASKED_TEXT_PLACEHOLDER, "")

    # Validate password only if it's not the placeholder (i.e., user is setting a new password)
    if not password_is_placeholder and len(password) < 8:
        errors.append("Password must be at least 8 characters")

    # For new config creation, password is required (can't use placeholder or empty)
    if not config and password_is_placeholder:
        errors.append("Password is required for new configuration")

    if errors:
        return templates.TemplateResponse(
            request,
            name="admin/house.html",
            context={
                "errors": errors,
                "house_name": name,
                "house_code": code,
                "house_password": MASKED_TEXT_PLACEHOLDER if password else "",
                "success_message": None,
            },
        )

    # Build update data - exclude password if placeholder was submitted
    house_config_data = {"name": name, "code": code}
    if not password_is_placeholder:
        house_config_data["password"] = password

    house_config = HouseConfigCreate(**house_config_data)

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
    users = await list_records(collection="users", per_page=1000, sort="-created")
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
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return templates.TemplateResponse(
        request,
        name="admin/member_row.html",
        context={"member": user},
    )


@router.get("/members/add")
async def get_add_member(request: Request, _auth: None = Depends(require_auth)) -> Response:
    """Render add member form."""
    success_message = request.cookies.get("flash_success")
    return templates.TemplateResponse(
        request, name="admin/add_member.html", context={"success_message": success_message}
    )


@router.post("/members/add")
async def post_add_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str = Form(...),
) -> Response:
    """Process add member form and send WhatsApp invite."""
    errors = []

    # Validate E.164 format
    if not phone or not phone.startswith("+"):
        errors.append("Phone number must be in E.164 format (e.g., +1234567890)")
    elif len(phone) < 8 or len(phone) > 16:
        errors.append("Phone number must be 8-15 digits with + prefix")

    if errors:
        return templates.TemplateResponse(
            request,
            name="admin/add_member.html",
            context={"errors": errors, "phone": phone},
        )

    # Check if user already exists
    existing_user = await get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )
    if existing_user:
        return templates.TemplateResponse(
            request,
            name="admin/add_member.html",
            context={"errors": ["User already exists"], "phone": phone},
        )

    # Get house config for welcome message
    config = await get_house_config_from_service()
    house_name = config.name

    # Generate email from phone for PocketBase auth collection requirement
    email = f"{phone.replace('+', '').replace('-', '')}@choresir.local"

    # Generate secure random password for initial account creation
    temp_password = secrets.token_urlsafe(32)

    # Create user record
    user_create = UserCreate(
        phone=phone,
        name="Pending User",
        email=email,
        role=UserRole.MEMBER,
        status=UserStatus.PENDING,
        password=temp_password,
        passwordConfirm=temp_password,
    )

    created_user = await create_record(collection="users", data=user_create.model_dump())
    logger.info("created_pending_user", extra={"phone": phone})

    # Send WhatsApp invite message
    invite_message = f"You've been invited to {house_name}! Reply YES to confirm"
    send_result = await send_text_message(to_phone=phone, text=invite_message)

    # Rollback user creation if WhatsApp send fails
    if not send_result.success:
        await delete_record(collection="users", record_id=created_user["id"])
        logger.warning(
            "user_creation_rolled_back_whatsapp_send_failed",
            extra={"phone": phone, "reason": send_result.error},
        )
        return templates.TemplateResponse(
            request,
            name="admin/add_member.html",
            context={"errors": [f"Failed to send WhatsApp message: {send_result.error}"], "phone": phone},
        )

    # Delete any existing pending invite (from previous attempts)
    existing_invite = await get_first_record(
        collection="pending_invites",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )
    if existing_invite:
        await delete_record(collection="pending_invites", record_id=existing_invite["id"])
        logger.info("deleted_stale_pending_invite", extra={"phone": phone})

    # Create pending invite record
    invite_create = InviteCreate(
        phone=phone,
        invited_at=datetime.now(UTC).isoformat(),
        invite_message_id=send_result.message_id,
    )
    await create_record(collection="pending_invites", data=invite_create.model_dump(exclude_none=True))
    logger.info("pending_invite_created", extra={"phone": phone})

    response = RedirectResponse(url="/admin/members", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("flash_success", "Invite sent", max_age=5)
    return response


@router.get("/members/{phone}/edit")
async def get_edit_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
) -> Response:
    """Render edit member form (inline for HTMX, full page otherwise)."""
    user = await get_first_record(
        collection="users",
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
            collection="users",
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
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update user record using DTO
    member_update = MemberUpdate(name=name.strip(), role=role)
    await update_record(
        collection="users",
        record_id=user["id"],
        data=member_update.model_dump(),
    )
    logger.info("member_updated", extra={"phone": phone, "name": name, "role": role})

    # Re-fetch user data to get updated values for HTMX response
    user = await get_first_record(
        collection="users",
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
        collection="users",
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
        collection="users",
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
    await delete_record(collection="users", record_id=user["id"])
    logger.info("removed_member", extra={"phone": phone})

    # Clean up any pending invite for this phone
    pending_invite = await get_first_record(
        collection="pending_invites",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )
    if pending_invite:
        await delete_record(collection="pending_invites", record_id=pending_invite["id"])
        logger.info("deleted_pending_invite_on_member_removal", extra={"phone": phone})

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
    import os

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


@router.get("/whatsapp/group-config")
async def get_group_config(
    *,
    _auth: None = Depends(require_auth),
) -> dict:
    """Get the current group chat configuration."""
    config = await get_first_record(collection="house_config", filter_query="")
    group_chat_id = config.get("group_chat_id") if config else None
    return {"group_chat_id": group_chat_id}


@router.post("/whatsapp/group-config")
async def post_group_config(
    *,
    _auth: None = Depends(require_auth),
    group_chat_id: str = Form(""),
) -> dict:
    """Update the group chat configuration."""
    # Validate group ID format if provided
    group_chat_id = group_chat_id.strip()
    if group_chat_id and not group_chat_id.endswith("@g.us"):
        return {"success": False, "error": "Group ID must end with @g.us (e.g., 120363400136168625@g.us)"}

    config = await get_first_record(collection="house_config", filter_query="")

    if not config:
        return {"success": False, "error": "House configuration not found. Please configure house settings first."}

    # Update the group_chat_id (empty string means clear it)
    await update_record(
        collection="house_config",
        record_id=config["id"],
        data={"group_chat_id": group_chat_id if group_chat_id else None},
    )

    if group_chat_id:
        logger.info("group_chat_id_configured", extra={"group_chat_id": group_chat_id})
        return {"success": True, "message": "Group chat configured successfully"}
    logger.info("group_chat_id_cleared")
    return {"success": True, "message": "Group chat configuration cleared. Bot will respond to DMs only."}
