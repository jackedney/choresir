"""FastHTML admin application factory with auth beforeware."""

from __future__ import annotations

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
    """Create and return a FastHTML admin app with auth and all routes registered."""

    def auth_before(req, sess):
        auth = req.scope["auth"] = sess.get("admin_user", None)
        if not auth:
            return RedirectResponse("/admin/login", status_code=303)

    beforeware = Beforeware(
        auth_before,
        skip=[r"/admin/login", r"/admin/login/submit"],
    )

    app, rt = fast_app(before=beforeware, secret_key=settings.admin_secret)

    register_pages(rt, session_factory, settings, waha_client)

    return app
