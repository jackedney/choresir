"""FastHTML admin application factory with auth beforeware."""

from __future__ import annotations

from fasthtml.common import Beforeware, RedirectResponse, fast_app
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.admin.pages import register_pages
from choresir.config import Settings


def _auth_before(req, sess):
    """Auth validation beforeware."""
    auth = req.scope["auth"] = sess.get("admin_user", None)
    if not auth:
        return RedirectResponse("/admin/login", status_code=303)


def create_admin_app(
    settings: Settings,
    session_factory: async_sessionmaker,
):
    """Create and return a FastHTML admin app with auth and routes."""
    beforeware = Beforeware(
        _auth_before,
        skip=[r"/admin/login", r"/admin/login/submit"],
    )

    app, rt = fast_app(before=beforeware, secret_key=settings.admin_secret)

    register_pages(rt, session_factory, settings)

    return app
