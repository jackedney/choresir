with open("tests/security/test_admin_rate_limit.py", "r") as f:
    content = f.read()

# FastHTML uses absolute paths, we need to prefix /login with /admin/login when making requests?
# Actually no, @rt("/login") is registered under /admin by convention? Or maybe not. Let's look at how the app is mounted or what the actual route is.
# Looking at the routes, @rt("/login") means the route is literally "/login" in the FastHTML app. The wrapper may mount it under /admin or we just call /login/submit.

content = content.replace('"/admin/login/submit"', '"/login/submit"')
content = content.replace('"/admin/login?error=1"', '"/login?error=1"')
content = content.replace('"/admin/login?error=ratelimit"', '"/login?error=ratelimit"')
content = content.replace('"/admin"', '"/"')

with open("tests/security/test_admin_rate_limit.py", "w") as f:
    f.write(content)
