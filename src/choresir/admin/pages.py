"""Admin page handlers registered on the FastHTML route decorator."""

from __future__ import annotations

from fasthtml.common import *  # noqa: F403 — FastHTML convention
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.config import Settings
from choresir.enums import MemberRole
from choresir.services.member_service import MemberService
from choresir.services.messaging import WAHAClient


def _get_csrf_token(sess) -> str:
    """Get or create CSRF token from session."""
    token = sess.get("csrf_token")
    if not token:
        import secrets

        token = secrets.token_urlsafe(32)
        sess["csrf_token"] = token
    return token


def register_pages(
    rt,
    session_factory: async_sessionmaker,
    settings: Settings,
    waha_client: WAHAClient,
) -> None:
    """Register all admin page routes on the given FastHTML route decorator."""

    @rt("/")
    def get():
        return Titled(  # noqa: F405
            "Admin Dashboard",
            Div(  # noqa: F405
                P(A("Members", href="/admin/members")),  # noqa: F405
                P(A("Household Settings", href="/admin/settings")),  # noqa: F405
                P(A("WAHA Session", href="/admin/waha")),  # noqa: F405
                P(A("Logout", href="/admin/logout")),  # noqa: F405
            ),
        )

    @rt("/login")
    def login_get():
        return Titled(  # noqa: F405
            "Login",
            Form(  # noqa: F405
                Input(name="username", placeholder="Username"),  # noqa: F405
                Input(name="password", type="password", placeholder="Password"),  # noqa: F405
                Button("Login"),  # noqa: F405
                action="/admin/login/submit",
                method="POST",
            ),
        )

    @rt("/login/submit")
    def login_post(username: str, password: str, sess):
        if username == settings.admin_user and password == settings.admin_password:
            sess["admin_user"] = username
            return RedirectResponse("/admin", status_code=303)  # noqa: F405
        return RedirectResponse("/admin/login?error=1", status_code=303)  # noqa: F405

    @rt("/logout")
    def logout_get(sess):
        sess.pop("admin_user", None)
        return RedirectResponse("/admin/login", status_code=303)  # noqa: F405

    @rt("/members")
    async def members_get(sess):
        async with session_factory() as session:
            svc = MemberService(session)
            members = await svc.list_all()

        rows = [
            Tr(  # noqa: F405
                Td(m.name or "(unnamed)"),  # noqa: F405
                Td(m.role),  # noqa: F405
                Td(m.status),  # noqa: F405
                Td(  # noqa: F405
                    Form(  # noqa: F405
                        Input(  # noqa: F405
                            name="csrf_token",
                            type="hidden",
                            value=_get_csrf_token(sess),
                        ),
                        Input(  # noqa: F405
                            name="role",
                            value="admin" if m.role == MemberRole.MEMBER else "member",
                            type="hidden",
                        ),
                        Button(  # noqa: F405
                            "Make Admin"
                            if m.role == MemberRole.MEMBER
                            else "Make Member"
                        ),
                        action=f"/admin/members/{m.id}/role",
                        method="POST",
                    ),
                ),
            )
            for m in members
        ]

        return Titled(  # noqa: F405
            "Members",
            Table(  # noqa: F405
                Tr(Th("Name"), Th("Role"), Th("Status"), Th("Action")),  # noqa: F405
                *rows,
            ),
            P(A("Back to Dashboard", href="/admin")),  # noqa: F405
        )

    @rt("/members/{member_id}/role")
    async def member_role_post(member_id: int, role: str, sess):
        member_role = MemberRole(role)
        async with session_factory() as session:
            svc = MemberService(session)
            await svc.set_role(member_id, member_role)

        return RedirectResponse("/admin/members", status_code=303)  # noqa: F405

    @rt("/settings")
    def settings_get():
        return Titled(  # noqa: F405
            "Household Settings",
            P("Household settings configuration coming soon."),  # noqa: F405
            P(A("Back to Dashboard", href="/admin")),  # noqa: F405
        )

    @rt("/waha")
    async def waha_get(sess):
        status_text = "Unknown"
        try:
            resp = await waha_client._http.get(
                f"{waha_client._base_url}/api/sessions/default/status",
                headers={"X-Api-Key": waha_client._api_key},
            )
            resp.raise_for_status()
            status_text = resp.text
        except Exception as exc:  # noqa: BLE001
            status_text = f"Error fetching status: {exc}"

        return Titled(  # noqa: F405
            "WAHA Session",
            P(f"Session status: {status_text}"),  # noqa: F405
            Form(  # noqa: F405
                Input(name="csrf_token", type="hidden", value=_get_csrf_token(sess)),  # noqa: F405
                Button("Start Session"),  # noqa: F405
                action="/admin/waha/start",
                method="POST",
            ),
            P(A("Back to Dashboard", href="/admin")),  # noqa: F405
        )

    @rt("/waha/start")
    async def waha_start_post(sess):
        try:
            resp = await waha_client._http.post(
                f"{waha_client._base_url}/api/sessions/start",
                json={"name": "default"},
                headers={"X-Api-Key": waha_client._api_key},
            )
            resp.raise_for_status()
        except Exception:  # noqa: BLE001, S110 # nosec B110
            pass

        return RedirectResponse("/admin/waha", status_code=303)  # noqa: F405
