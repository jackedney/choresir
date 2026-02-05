"""Admin interface router for web UI."""

import logging
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.core.config import constants, settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-session")


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
    return templates.TemplateResponse(request, name="admin/dashboard.html")


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
