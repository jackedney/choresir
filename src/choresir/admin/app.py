"""FastHTML admin application factory with auth and CSRF beforeware."""

from __future__ import annotations

import secrets

from fasthtml.common import Beforeware, RedirectResponse, fast_app
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.admin.pages import register_pages
from choresir.config import Settings
from choresir.services.messaging import WAHAClient


def create_admin_app(
    settings: Settings,
    session_factory: async_sessionmaker,
    waha_client: WAHAClient,
):
    """Create and return a FastHTML admin app with auth, CSRF, and routes."""

    def csrf_before(req, sess):
        if req.method in ("POST", "PUT", "DELETE", "PATCH"):
            session_token = sess.get("csrf_token")
            form_token = None

            content_type = req.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = getattr(req, "_form", None)
                if form:
                    form_token = form.get("csrf_token")

            if not form_token:
                form_token = req.headers.get("X-CSRF-Token")

            if (
                not session_token
                or not form_token
                or not secrets.compare_digest(session_token, form_token)
            ):
                return RedirectResponse("/admin?csrf_error=1", status_code=403)

    def auth_before(req, sess):
        auth = req.scope["auth"] = sess.get("admin_user", None)
        if not auth:
            return RedirectResponse("/admin/login", status_code=303)

    csrfware = Beforeware(
        csrf_before,
        skip=[r"/admin/login", r"/admin/login/submit"],
    )

    beforeware = Beforeware(
        auth_before,
        skip=[r"/admin/login", r"/admin/login/submit"],
    )

    app, rt = fast_app(before=(csrfware, beforeware), secret_key=settings.admin_secret)

    register_pages(rt, session_factory, settings, waha_client)

    return app
