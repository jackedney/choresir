import re

with open("src/choresir/admin/pages.py", "r") as f:
    content = f.read()

# Add standard library imports where appropriate
content = content.replace("import logging\nimport secrets as _secrets", "import logging\nimport secrets as _secrets\nimport threading")

# Add the constants and dictionary before the pages registration
rate_limit_code = """
# Rate limiting for admin login
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60
MAX_TRACKED_IPS = 1000


def _build_auth_routes(rt, settings: Settings) -> None:
"""

content = content.replace("def _build_auth_routes(rt, settings: Settings) -> None:", rate_limit_code)

login_post_new = """    @rt("/login/submit")
    def login_post(username: str, password: str, sess, req):
        ip = req.client.host if req.client else "unknown"
        now = time.monotonic()

        with _login_lock:
            # Clean up old attempts for this IP
            attempts = [
                t for t in _login_attempts.get(ip, [])
                if now - t < LOGIN_WINDOW_SECONDS
            ]

            if len(attempts) >= MAX_LOGIN_ATTEMPTS:
                # Rate limit exceeded
                return RedirectResponse("/admin/login?error=ratelimit", status_code=303)  # noqa: F405

            attempts.append(now)
            _login_attempts[ip] = attempts

            # Bounding the dictionary size safely
            if len(_login_attempts) > MAX_TRACKED_IPS:
                del _login_attempts[next(iter(_login_attempts))]

        user_match = _secrets.compare_digest(username, settings.admin_user)
        pass_match = _secrets.compare_digest(password, settings.admin_password)

        if user_match and pass_match:
            with _login_lock:
                if ip in _login_attempts:
                    del _login_attempts[ip]
            sess["admin_user"] = username
            return RedirectResponse("/admin", status_code=303)  # noqa: F405
        return RedirectResponse("/admin/login?error=1", status_code=303)  # noqa: F405"""

content = re.sub(r'    @rt\("/login/submit"\)\n    def login_post\(.*?return RedirectResponse\("/admin/login\?error=1", status_code=303\)  # noqa: F405', login_post_new, content, flags=re.DOTALL)

with open("src/choresir/admin/pages.py", "w") as f:
    f.write(content)
