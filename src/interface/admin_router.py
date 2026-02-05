"""Admin interface router for web UI."""

import logging
import secrets

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer

from src.core.config import constants, settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

serializer = URLSafeTimedSerializer(str(settings.secret_key), salt="admin-session")


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
