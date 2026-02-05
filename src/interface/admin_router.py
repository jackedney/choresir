"""Admin interface router for web UI."""

import logging
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.core.config import constants, settings
from src.core.db_client import create_record, get_first_record, list_records, update_record
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

    return templates.TemplateResponse(request, name="admin/members.html", context={"members": users})
