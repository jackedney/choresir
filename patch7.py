with open("tests/security/test_admin_rate_limit.py", "r") as f:
    content = f.read()

# Since the skip for beforeware is r"/admin/login", r"/admin/login/submit",
# if we call "/login/submit" without "/admin", the beforeware will block it and redirect to /admin/login!
# The app is not mounted under /admin internally in the app object? Let's check how the main app mounts it.
# Wait, if we use route "/login/submit" in tests, we should either mock the mount or make it match the skip list.
# Let's see: `skip=[r"/admin/login", r"/admin/login/submit"]` is exactly what app.py has. But `register_pages(rt)` maps it to `@rt("/login")` which means the route path is just "/login".
# If the request comes in as "/login/submit", the beforeware regex `r"/admin/login/submit"` won't match, so it redirects to `RedirectResponse("/admin/login")`.
# Let's adjust our test client to make requests to `/admin/login/submit`. To do that, the FastHTML app must have a route for `/admin/login/submit`, but wait, does it?
# In FastHTML, if you mount the app in FastAPI, the path includes the prefix. In our standalone test, the prefix is missing unless we add it or the test client includes it.
# Or we can just use the exact routes in pages.py: `response.headers["location"] == "/admin/login?error=1"` is what pages.py explicitly returns.

content = content.replace('"/login/submit"', '"/admin/login/submit"')
content = content.replace('"/login?error=1"', '"/admin/login?error=1"')
content = content.replace('"/login?error=ratelimit"', '"/admin/login?error=ratelimit"')
content = content.replace('"/?"', '"/admin"')
content = content.replace('"/admin/"', '"/admin"') # fix

with open("tests/security/test_admin_rate_limit.py", "w") as f:
    f.write(content)
