"""Admin page handlers registered on the FastHTML route decorator."""

from __future__ import annotations

import logging
import secrets as _secrets
import time
from datetime import UTC, datetime

import httpx
from fasthtml.common import *  # noqa: F403 — FastHTML convention
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.config import Settings
from choresir.enums import (
    MemberRole,
    TaskStatus,
    TaskVisibility,
    VerificationMode,
)
from choresir.errors import RateLimitExceededError
from choresir.services.member_service import MemberService
from choresir.services.messaging import NullSender
from choresir.services.task_service import TaskService

logger = logging.getLogger(__name__)


def _get_csrf_token(sess) -> str:
    """Get or create CSRF token for the session."""
    token = sess.get("_csrf_token")
    if not token:
        token = _secrets.token_hex(16)
        sess["_csrf_token"] = token
    return token


def _validate_csrf(sess, token: str | None) -> bool:
    """Validate CSRF token matches session."""
    if not token:
        return False
    return sess.get("_csrf_token") == token


def _csrf_input(sess):
    """Hidden input field with CSRF token."""
    return Input(name="_csrf", type="hidden", value=_get_csrf_token(sess))  # noqa: F405


def _check_csrf(sess, csrf_token: str):
    """Validate CSRF or redirect to login."""
    if not _validate_csrf(sess, csrf_token):
        raise ValueError("Invalid CSRF token")


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
                _csrf_input(sess),
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
        _csrf: str = "",
        household_name: str = "",
        verification_mode: str = VerificationMode.NONE.value,
        daily_summary_time: str = "20:00",
        weekly_leaderboard_day: str = "sunday",
        weekly_leaderboard_time: str = "20:00",
    ):
        _check_csrf(sess, _csrf)
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
                    _csrf_input(sess),
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
                _csrf_input(sess),
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
    async def waha_restart_post(_csrf: str, sess):
        _check_csrf(sess, _csrf)
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
            logger.error("WAHA restart error: %s", exc)

        return RedirectResponse("/admin/waha", status_code=303)  # noqa: F405

    @rt("/waha/start")
    async def waha_start_post(_csrf: str, sess):
        _check_csrf(sess, _csrf)
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    f"{settings.waha_url}/api/sessions/default/start",
                    headers={"X-Api-Key": settings.waha_api_key},
                    timeout=10.0,
                )
                resp.raise_for_status()
                logger.info("WAHA start response: %d - %s", resp.status_code, resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.error("WAHA start error: %s", exc)

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
                        _csrf_input(sess),
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
    async def member_role_post(member_id: int, role: str, _csrf: str, sess):
        _check_csrf(sess, _csrf)
        member_role = MemberRole(role)
        async with session_factory() as session:
            svc = MemberService(session)
            await svc.set_role(member_id, member_role)

        return RedirectResponse("/admin/members", status_code=303)  # noqa: F405


def _build_tasks_routes(
    rt, session_factory: async_sessionmaker, settings: Settings
) -> None:
    """Register tasks page routes."""

    @rt("/tasks")
    async def tasks_get(sess):
        async with session_factory() as session:
            member_svc = MemberService(session)
            task_svc = TaskService(
                session, NullSender(), settings.max_takeovers_per_week
            )
            tasks = await task_svc.list_tasks()
            members = await member_svc.list_all()

        member_map = {m.id: m.name or "(unnamed)" for m in members}

        rows = [
            Tr(  # noqa: F405
                Td(t.title),  # noqa: F405
                Td(member_map.get(t.assignee_id, "Unknown")),  # noqa: F405
                Td(t.status),  # noqa: F405
                Td(t.visibility),  # noqa: F405
                Td(t.deadline.strftime("%Y-%m-%d %H:%M") if t.deadline else "-"),  # noqa: F405
                Td(  # noqa: F405
                    A(  # noqa: F405
                        "Edit",
                        href=f"/admin/tasks/{t.id}/edit",
                        style="margin-right:0.5rem",
                    ),  # noqa: F405
                    A("Delete", href=f"/admin/tasks/{t.id}/delete"),  # noqa: F405
                ),
            )
            for t in tasks
        ]

        return Titled(  # noqa: F405
            "Tasks",
            Table(  # noqa: F405
                Tr(  # noqa: F405
                    Th("Title"),  # noqa: F405
                    Th("Assignee"),  # noqa: F405
                    Th("Status"),  # noqa: F405
                    Th("Visibility"),  # noqa: F405
                    Th("Deadline"),  # noqa: F405
                    Th("Actions"),  # noqa: F405
                ),  # noqa: F405
                *rows,
            ),
            P(A("Back to Dashboard", href="/admin")),  # noqa: F405
        )

    @rt("/tasks/{task_id}/edit")
    async def task_edit_get(task_id: int, sess):
        async with session_factory() as session:
            member_svc = MemberService(session)
            task_svc = TaskService(
                session, NullSender(), settings.max_takeovers_per_week
            )
            task = await task_svc.get_task(task_id)
            members = await member_svc.list_all()

        member_options = [
            Option(  # noqa: F405
                m.name or "(unnamed)",
                value=str(m.id),
                selected=m.id == task.assignee_id,
            )
            for m in members
        ]

        status_options = [
            Option(  # noqa: F405
                s.value,
                value=s.value,
                selected=s == task.status,
            )
            for s in TaskStatus
        ]

        visibility_options = [
            Option(  # noqa: F405
                v.value,
                value=v.value,
                selected=v == task.visibility,
            )
            for v in TaskVisibility
        ]

        verification_options = [
            Option(  # noqa: F405
                v.value,
                value=v.value,
                selected=v == task.verification_mode,
            )
            for v in VerificationMode
        ]

        deadline_value = (
            task.deadline.strftime("%Y-%m-%dT%H:%M") if task.deadline else ""
        )

        return Titled(  # noqa: F405
            f"Edit Task: {task.title}",
            Form(  # noqa: F405
                _csrf_input(sess),
                Div(  # noqa: F405
                    Label("Title", For="title"),  # noqa: F405
                    Input(name="title", id="title", value=task.title),  # noqa: F405
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Description", For="description"),  # noqa: F405
                    Textarea(  # noqa: F405
                        task.description or "",
                        name="description",
                        id="description",
                        rows=3,
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Assignee", For="assignee_id"),  # noqa: F405
                    Select(  # noqa: F405
                        member_options,
                        name="assignee_id",
                        id="assignee_id",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Status", For="status"),  # noqa: F405
                    Select(  # noqa: F405
                        status_options,
                        name="status",
                        id="status",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Verification Mode", For="verification_mode"),  # noqa: F405
                    Select(  # noqa: F405
                        verification_options,
                        name="verification_mode",
                        id="verification_mode",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Visibility", For="visibility"),  # noqa: F405
                    Select(  # noqa: F405
                        visibility_options,
                        name="visibility",
                        id="visibility",
                    ),
                    style="margin-bottom:1rem",
                ),
                Div(  # noqa: F405
                    Label("Deadline", For="deadline"),  # noqa: F405
                    Input(  # noqa: F405
                        name="deadline",
                        id="deadline",
                        type="datetime-local",
                        value=deadline_value,
                    ),
                    style="margin-bottom:1rem",
                ),
                Button("Save Changes", cls="primary"),  # noqa: F405
                action=f"/admin/tasks/{task_id}/edit",
                method="POST",
            ),
            P(A("Cancel", href="/admin/tasks"), style="margin-top:1.5rem"),  # noqa: F405
        )

    @rt("/tasks/{task_id}/edit")
    async def task_edit_post(
        task_id: int,
        _csrf: str,
        title: str,
        description: str = "",
        assignee_id: int = 0,
        status: str = "pending",
        verification_mode: str = "none",
        visibility: str = "shared",
        deadline: str = "",
        sess=None,
    ):
        _check_csrf(sess, _csrf)
        async with session_factory() as session:
            task_svc = TaskService(
                session, NullSender(), settings.max_takeovers_per_week
            )
            task = await task_svc.get_task(task_id)

            task.title = title
            task.description = description if description else None
            task.assignee_id = assignee_id
            task.status = TaskStatus(status)
            task.verification_mode = VerificationMode(verification_mode)
            task.visibility = TaskVisibility(visibility)
            task.deadline = (
                datetime.fromisoformat(deadline).replace(tzinfo=UTC)
                if deadline
                else None
            )
            task.updated_at = datetime.now(UTC)

            session.add(task)
            await session.commit()

        return RedirectResponse("/admin/tasks", status_code=303)  # noqa: F405

    @rt("/tasks/{task_id}/delete")
    async def task_delete_get(task_id: int, sess):
        async with session_factory() as session:
            task_svc = TaskService(
                session, NullSender(), settings.max_takeovers_per_week
            )
            task = await task_svc.get_task(task_id)

        return Titled(  # noqa: F405
            f"Delete Task: {task.title}",
            P(  # noqa: F405
                f"Are you sure you want to delete '{task.title}'?",
                style="margin-bottom:1rem",
            ),  # noqa: F405
            Form(  # noqa: F405
                _csrf_input(sess),
                Button("Delete", cls="primary", style="background-color:#dc3545"),  # noqa: F405
                action=f"/admin/tasks/{task_id}/delete",
                method="POST",
            ),
            P(A("Cancel", href="/admin/tasks"), style="margin-top:1rem"),  # noqa: F405
        )

    @rt("/tasks/{task_id}/delete")
    async def task_delete_post(task_id: int, _csrf: str, sess):
        _check_csrf(sess, _csrf)
        async with session_factory() as session:
            task_svc = TaskService(
                session, NullSender(), settings.max_takeovers_per_week
            )
            task = await task_svc.get_task(task_id)
            await session.delete(task)
            await session.commit()

        return RedirectResponse("/admin/tasks", status_code=303)  # noqa: F405


_login_attempts: dict[str, list[float]] = {}


def _build_auth_routes(rt, settings: Settings) -> None:
    """Register authentication page routes.

    Note: Login form intentionally omits CSRF protection because there is no
    authenticated session at login time. CSRF attacks require an existing
    session to exploit. This is standard practice for login forms.
    """

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
    def login_post(req, username: str, password: str, sess):
        global _login_attempts

        # Prevent memory exhaustion
        if len(_login_attempts) > 1000:
            _login_attempts.clear()

        client_ip = getattr(req.client, "host", "unknown")
        now = time.time()

        # Clean up old attempts for this IP
        if client_ip in _login_attempts:
            _login_attempts[client_ip] = [
                t for t in _login_attempts[client_ip] if now - t < 60
            ]

        attempts = _login_attempts.get(client_ip, [])
        if len(attempts) >= 5:
            raise RateLimitExceededError()

        attempts.append(now)
        _login_attempts[client_ip] = attempts

        user_match = _secrets.compare_digest(username, settings.admin_user)
        pass_match = _secrets.compare_digest(password, settings.admin_password)

        if user_match and pass_match:
            sess["admin_user"] = username
            # On successful login, clear attempts for this IP
            if client_ip in _login_attempts:
                del _login_attempts[client_ip]
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
                P(A("Tasks", href="/admin/tasks")),  # noqa: F405
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
    _build_tasks_routes(rt, session_factory, settings)
    _build_settings_routes(rt, settings)
    _build_waha_routes(rt, settings)
