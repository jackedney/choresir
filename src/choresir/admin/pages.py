"""Admin page handlers registered on the FastHTML route decorator."""

from __future__ import annotations

import time

import httpx
from fasthtml.common import *  # noqa: F403 — FastHTML convention
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.config import Settings
from choresir.enums import MemberRole, VerificationMode
from choresir.services.member_service import MemberService


def _build_settings_routes(rt, settings: Settings) -> None:
    """Register settings page routes."""
    days = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    @rt("/settings")
    def settings_get(sess, saved: str = ""):
        household_name = sess.get("household_name", "")
        max_takeovers = settings.max_takeovers_per_week
        verification_mode = sess.get("verification_mode", VerificationMode.NONE.value)
        daily_summary_time = sess.get("daily_summary_time", "20:00")
        weekly_leaderboard_day = sess.get("weekly_leaderboard_day", "sunday")
        weekly_leaderboard_time = sess.get("weekly_leaderboard_time", "20:00")

        mode_options = [
            Option(  # noqa: F405
                "None (no verification required)",
                value=VerificationMode.NONE.value,
                selected=verification_mode == VerificationMode.NONE.value,
            ),
            Option(  # noqa: F405
                "Peer (any member can verify)",
                value=VerificationMode.PEER.value,
                selected=verification_mode == VerificationMode.PEER.value,
            ),
            Option(  # noqa: F405
                "Partner (assigned partner verifies)",
                value=VerificationMode.PARTNER.value,
                selected=verification_mode == VerificationMode.PARTNER.value,
            ),
        ]

        day_options = [
            Option(  # noqa: F405
                day.capitalize(),
                value=day,
                selected=weekly_leaderboard_day == day,
            )
            for day in days
        ]

        success_msg = (
            P("Settings saved successfully!", style="color:green;margin-bottom:1rem")  # noqa: F405
            if saved == "1"
            else None
        )

        return Titled(  # noqa: F405
            "Household Settings",
            success_msg,
            Form(  # noqa: F405
                Div(  # noqa: F405
                    Label("Household Name", For="household_name"),  # noqa: F405
                    Input(  # noqa: F405
                        name="household_name",
                        id="household_name",
                        value=household_name,
                        placeholder="e.g., The Smith Family",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Max Takeovers per Week", For="max_takeovers"),  # noqa: F405
                    P(  # noqa: F405
                        f"Current limit: {max_takeovers} "
                        "(configured via CHORESIR_MAX_TAKEOVERS_PER_WEEK)",
                        style="font-size:0.85rem;color:#666;margin-top:0.25rem",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Default Verification Mode", For="verification_mode"),  # noqa: F405
                    Select(  # noqa: F405
                        mode_options,
                        name="verification_mode",
                        id="verification_mode",
                    ),
                    style="margin-bottom:1rem",
                ),
                Fieldset(  # noqa: F405
                    Legend("Daily Summary"),  # noqa: F405
                    Div(  # noqa: F405
                        Label("Time", For="daily_summary_time"),  # noqa: F405
                        Input(  # noqa: F405
                            name="daily_summary_time",
                            id="daily_summary_time",
                            type="time",
                            value=daily_summary_time,
                        ),
                        style="margin-top:0.5rem",
                    ),
                    style="margin-bottom:1rem",
                ),
                Fieldset(  # noqa: F405
                    Legend("Weekly Leaderboard"),  # noqa: F405
                    Div(  # noqa: F405
                        Label("Day", For="weekly_leaderboard_day"),  # noqa: F405
                        Select(  # noqa: F405
                            day_options,
                            name="weekly_leaderboard_day",
                            id="weekly_leaderboard_day",
                        ),
                        style="margin-top:0.5rem",
                    ),
                    Div(  # noqa: F405
                        Label("Time", For="weekly_leaderboard_time"),  # noqa: F405
                        Input(  # noqa: F405
                            name="weekly_leaderboard_time",
                            id="weekly_leaderboard_time",
                            type="time",
                            value=weekly_leaderboard_time,
                        ),
                        style="margin-top:0.5rem",
                    ),
                    style="margin-bottom:1rem",
                ),
                Button("Save Settings", cls="primary"),  # noqa: F405
                action="/admin/settings",
                method="POST",
            ),
            P(A("← Back to Dashboard", href="/admin"), style="margin-top:1.5rem"),  # noqa: F405
        )

    @rt("/settings")
    def settings_post(
        sess,
        household_name: str = "",
        verification_mode: str = VerificationMode.NONE.value,
        daily_summary_time: str = "20:00",
        weekly_leaderboard_day: str = "sunday",
        weekly_leaderboard_time: str = "20:00",
    ):
        sess["household_name"] = household_name
        sess["verification_mode"] = verification_mode
        sess["daily_summary_time"] = daily_summary_time
        sess["weekly_leaderboard_day"] = weekly_leaderboard_day
        sess["weekly_leaderboard_time"] = weekly_leaderboard_time

        return RedirectResponse("/admin/settings?saved=1", status_code=303)  # noqa: F405


def _build_waha_routes(rt, settings: Settings) -> None:
    """Register WAHA session page routes."""

    @rt("/waha")
    async def waha_get(sess):
        status_text = "Unknown"
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    f"{settings.waha_url}/api/sessions/default",
                    headers={"X-Api-Key": settings.waha_api_key},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                status_text = data.get("status", "Unknown")
        except Exception as exc:  # noqa: BLE001
            status_text = f"Error fetching status: {exc}"

        is_connected = status_text == "WORKING"
        is_qr = status_text == "SCAN_QR_CODE"
        status_color = "green" if is_connected else "orange" if is_qr else "red"

        qr_section = Div()  # noqa: F405
        if is_qr:
            qr_section = Card(  # noqa: F405
                Div(  # noqa: F405
                    id="qr-container",
                    hx_get="/admin/waha/qr-fragment",
                    hx_trigger="every 5s",
                    hx_swap="innerHTML",
                    style="text-align:center",
                )(
                    Img(  # noqa: F405
                        src="/admin/waha/qr",
                        alt="QR Code",
                        style="max-width:100%;border-radius:8px",
                    ),
                ),
                P(  # noqa: F405
                    "Open WhatsApp on your phone, go to ",
                    Strong("Settings → Linked Devices → Link a Device"),  # noqa: F405
                    ", and scan the QR code above.",
                    style="margin-top:1rem;font-size:0.9rem;color:#666",
                ),
                footer=Form(  # noqa: F405
                    Button(  # noqa: F405
                        "Reload QR Code",
                        cls="secondary outline",
                        style="width:100%",
                    ),
                    action="/admin/waha/restart",
                    method="POST",
                ),
            )

        actions = Div(  # noqa: F405
            Form(  # noqa: F405
                Button("Refresh", cls="outline", style="width:100%"),  # noqa: F405
                action="/admin/waha",
                method="GET",
            ),
            Form(  # noqa: F405
                Button("Start Session", cls="outline", style="width:100%"),  # noqa: F405
                action="/admin/waha/start",
                method="POST",
            ),
            style=(
                "display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-top:1rem"
            ),
        )

        return Titled(  # noqa: F405
            "WAHA Session",
            P(  # noqa: F405
                "Status: ",
                Strong(  # noqa: F405
                    status_text,
                    style=f"color:{status_color}",
                ),
            ),
            qr_section,
            actions,
            P(  # noqa: F405
                A("← Back to Dashboard", href="/admin"),  # noqa: F405
                style="margin-top:1.5rem",
            ),
        )

    @rt("/waha/qr-fragment")
    async def waha_qr_fragment_get(sess):
        return Img(src=f"/admin/waha/qr?t={int(time.time())}", alt="QR Code")  # noqa: F405

    @rt("/waha/qr")
    async def waha_qr_get(sess):
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{settings.waha_url}/api/screenshot?session=default",
                headers={"X-Api-Key": settings.waha_api_key},
                timeout=10.0,
            )
            resp.raise_for_status()
            return Response(  # noqa: F405
                content=resp.content,
                media_type="image/png",
            )

    @rt("/waha/restart")
    async def waha_restart_post(sess):
        try:
            async with httpx.AsyncClient() as http:
                await http.post(
                    f"{settings.waha_url}/api/sessions/default/stop",
                    headers={"X-Api-Key": settings.waha_api_key},
                    timeout=10.0,
                )
                await http.post(
                    f"{settings.waha_url}/api/sessions/default/start",
                    headers={"X-Api-Key": settings.waha_api_key},
                    timeout=10.0,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"WAHA restart error: {exc}")

        return RedirectResponse("/admin/waha", status_code=303)  # noqa: F405

    @rt("/waha/start")
    async def waha_start_post(sess):
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    f"{settings.waha_url}/api/sessions/default/start",
                    headers={"X-Api-Key": settings.waha_api_key},
                    timeout=10.0,
                )
                resp.raise_for_status()
                print(f"WAHA start response: {resp.status_code} - {resp.text}")
        except Exception as exc:  # noqa: BLE001
            print(f"WAHA start error: {exc}")

        return RedirectResponse("/admin/waha", status_code=303)  # noqa: F405


def _build_members_routes(
    rt, session_factory: async_sessionmaker, settings: Settings
) -> None:
    """Register members page routes."""

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


def _build_auth_routes(rt, settings: Settings) -> None:
    """Register authentication page routes."""

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


def _build_dashboard_route(rt) -> None:
    """Register dashboard page route."""

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


def register_pages(
    rt,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Register all admin page routes on the given FastHTML route decorator."""
    _build_dashboard_route(rt)
    _build_auth_routes(rt, settings)
    _build_members_routes(rt, session_factory, settings)
    _build_settings_routes(rt, settings)
    _build_waha_routes(rt, settings)
