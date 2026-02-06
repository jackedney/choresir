"""Admin interface router for web UI."""

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.core.config import constants, settings
from src.core.db_client import create_record, get_first_record, list_records, sanitize_param, update_record
from src.interface.whatsapp_sender import send_text_message
from src.services.house_config_service import get_house_config as get_house_config_from_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-session")

# Placeholder string for obscured text display
MASKED_TEXT_PLACEHOLDER = "********"


async def require_auth(request: Request) -> None:
    """Dependency that checks for a valid admin session.

    Raises HTTPException redirecting to login if session is invalid or missing.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: Redirects to /admin/login if authentication fails
    """
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
    """Render the admin dashboard (protected by auth).

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)

    Returns:
        Template response with dashboard content
    """
    config = await get_house_config_from_service()
    house_name = config["name"]

    users = await list_records(collection="users", per_page=1000)

    total_members = len(users)
    active_members = sum(1 for user in users if user.get("status") == "active")
    pending_members = sum(1 for user in users if user.get("status") == "pending")
    banned_members = sum(1 for user in users if user.get("status") == "banned")

    return templates.TemplateResponse(
        request,
        name="admin/dashboard.html",
        context={
            "house_name": house_name,
            "total_members": total_members,
            "active_members": active_members,
            "pending_members": pending_members,
            "banned_members": banned_members,
        },
    )


@router.get("/login")
async def get_login(request: Request) -> Response:
    """Render the admin login form."""
    return templates.TemplateResponse(request, name="admin/login.html")


@router.post("/login")
async def post_login(
    *,
    request: Request,
    response: Response,
    password: str = Form(...),
) -> Response:
    """Process admin login form submission.

    Args:
        request: FastAPI request object
        response: FastAPI response object
        password: Submitted password from form

    Returns:
        RedirectResponse to /admin on success, login page with error on failure
    """
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
            secure=False,
            samesite="strict",
            max_age=86400,
        )
        return response

    error = "Invalid password"
    return templates.TemplateResponse(request, name="admin/login.html", context={"error": error})


@router.get("/logout")
async def logout() -> Response:
    """Clear admin session and redirect to login.

    Returns:
        RedirectResponse to /admin/login with session cookie cleared
    """
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="admin_session", httponly=True, samesite="strict")
    logger.info("admin_logout_success")
    return response


@router.get("/house")
async def get_house_config(request: Request, _auth: None = Depends(require_auth)) -> Response:
    """Render house configuration form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)

    Returns:
        Template response with house config form
    """
    config = await get_first_record(collection="house_config", filter_query="")
    success_message = request.cookies.get("flash_success")

    if config:
        house_name = config.get("name") or ""
        house_code = config.get("code") or ""
        house_password = MASKED_TEXT_PLACEHOLDER
    else:
        default_config = await get_house_config_from_service()
        house_name = default_config["name"]
        house_code = default_config["code"]
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
    password: str = Form(...),
) -> Response:
    """Update house configuration.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        name: House name (1-50 chars)
        code: House code (4+ chars)
        password: House password (8+ chars)

    Returns:
        RedirectResponse to /admin/house on success, template with errors on validation failure
    """
    errors = []

    if len(name) < 1 or len(name) > 50:
        errors.append("Name must be between 1 and 50 characters")

    if len(password) < 8:
        errors.append("Password must be at least 8 characters")

    if len(code) < 4:
        errors.append("Code must be at least 4 characters")

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

    config = await get_first_record(collection="house_config", filter_query="")

    data = {"name": name, "password": password, "code": code}

    if config:
        await update_record(collection="house_config", record_id=config["id"], data=data)
        logger.info("house_config_updated", extra={"name": name})
        message = "House configuration updated successfully"
    else:
        await create_record(collection="house_config", data=data)
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
    """Render member list with status and role badges.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)

    Returns:
        Template response with member list table
    """
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
    """Get a single member row fragment for HTMX updates.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number of member

    Returns:
        Template response with member row fragment, or 404 if not found
    """
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
    """Render add member form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)

    Returns:
        Template response with add member form
    """
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
    """Process add member form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number in E.164 format

    Returns:
        RedirectResponse to /admin/members on success, template with errors on validation failure
    """
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
    house_name = config["name"]

    # Generate email from phone for PocketBase auth collection requirement
    email = f"{phone.replace('+', '').replace('-', '')}@choresir.local"

    # Generate secure random password for initial account creation
    temp_password = secrets.token_urlsafe(32)

    # Create user record
    user_data = {
        "phone": phone,
        "name": "Pending User",
        "email": email,
        "role": "member",
        "status": "pending",
        "password": temp_password,
        "passwordConfirm": temp_password,
    }

    await create_record(collection="users", data=user_data)
    logger.info("Created pending user: %s", phone)

    # Send WhatsApp invite message
    invite_message = f"You've been invited to {house_name}! Reply YES to confirm"
    send_result = await send_text_message(to_phone=phone, text=invite_message)

    # Create pending invite record
    invite_data = {
        "phone": phone,
        "invited_at": datetime.now(UTC).isoformat(),
        "invite_message_id": send_result.message_id,
    }
    await create_record(collection="pending_invites", data=invite_data)
    logger.info("Created pending invite for %s", phone)

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
    """Render edit member form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number of member to edit

    Returns:
        Template response with edit member form (inline if HTMX, full page otherwise), or 404 if not found
    """
    user = await get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if is_htmx_request(request):
        return templates.TemplateResponse(
            request,
            name="admin/edit_member_inline.html",
            context={"user": user},
        )

    return templates.TemplateResponse(
        request,
        name="admin/edit_member.html",
        context={"user": user},
    )


@router.post("/members/{phone}/edit")
async def post_edit_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
    name: str = Form(...),
    role: str = Form(...),
) -> Response:
    """Process edit member form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number of member to edit
        name: Member name (1-50 chars, Unicode letters/spaces/hyphens/apostrophes)
        role: Member role (admin or member)

    Returns:
        RedirectResponse to /admin/members on success, template with errors on validation failure
        For HTMX requests, returns the updated row fragment or inline form with errors
    """
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

        if is_htmx_request(request):
            return templates.TemplateResponse(
                request,
                name="admin/edit_member_inline.html",
                context={"errors": errors, "user": user, "name": name, "role": role},
            )

        return templates.TemplateResponse(
            request,
            name="admin/edit_member.html",
            context={"errors": errors, "user": user, "name": name, "role": role},
        )

    # Find user by phone
    user = await get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update user record
    await update_record(
        collection="users",
        record_id=user["id"],
        data={"name": name.strip(), "role": role},
    )
    logger.info("Updated member: %s, name=%s, role=%s", phone, name, role)

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
    """Render remove member confirmation page.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number of member to remove

    Returns:
        Template response with remove member confirmation (inline if HTMX, full page otherwise), or 404 if not found
    """
    user = await get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if is_htmx_request(request):
        return templates.TemplateResponse(
            request,
            name="admin/remove_member_inline.html",
            context={"user": user},
        )

    return templates.TemplateResponse(
        request,
        name="admin/remove_member.html",
        context={"user": user},
    )


@router.post("/members/{phone}/remove")
async def post_remove_member(
    *,
    request: Request,
    _auth: None = Depends(require_auth),
    phone: str,
) -> Response:
    """Process remove member form.

    Args:
        request: FastAPI request object
        _auth: Auth dependency (ensures user is logged in)
        phone: Phone number of member to remove

    Returns:
        RedirectResponse to /admin/members on success, template with errors on validation failure
        For HTMX requests, returns the banned row fragment or inline form with errors
    """
    # Find user by phone
    user = await get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent banning admins
    if user.get("role") == "admin":
        if is_htmx_request(request):
            return templates.TemplateResponse(
                request,
                name="admin/remove_member_inline.html",
                context={"errors": ["Cannot ban an admin"], "user": user},
            )
        return templates.TemplateResponse(
            request,
            name="admin/remove_member.html",
            context={"errors": ["Cannot ban an admin"], "user": user},
        )

    # Update user status to banned
    await update_record(
        collection="users",
        record_id=user["id"],
        data={"status": "banned"},
    )
    logger.info("Banned member: %s", phone)

    if is_htmx_request(request):
        return templates.TemplateResponse(
            request,
            name="admin/member_row.html",
            context={"member": user},
        )

    response = RedirectResponse(url="/admin/members", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("flash_success", "Member banned", max_age=5)
    return response
