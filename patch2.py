import re

with open("src/choresir/admin/pages.py", "r") as f:
    content = f.read()

# Fix the import location
rate_limit_consts = """
# Rate limiting for admin login
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60
MAX_TRACKED_IPS = 1000
"""

content = content.replace(rate_limit_consts, "")

logger_line = "logger = logging.getLogger(__name__)\n\n"
content = content.replace(logger_line, logger_line + rate_limit_consts)

with open("src/choresir/admin/pages.py", "w") as f:
    f.write(content)
