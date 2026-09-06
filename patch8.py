import re

# Okay, in tests/security/test_admin_rate_limit.py, let's use a standard FastAPI mounting mechanism just like the real app probably does.
# Or wait, let's look at `src/choresir/main.py` to see how it's mounted.
with open("src/choresir/main.py", "r") as f:
    print("MAIN.PY:")
    print(f.read())
