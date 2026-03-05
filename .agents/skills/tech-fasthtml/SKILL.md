---
name: tech-fasthtml
description: Reference guide for FastHTML — pure Python admin web interface with auth and CSRF
user-invocable: false
---

# FastHTML

> Purpose: Admin web interface — member management, household config, WAHA session setup; pure Python, no JS templates
> Docs: https://fastht.ml / https://docs.fastht.ml
> Version researched: latest

## Quick Start

```python
from fasthtml.common import fast_app, Titled, P, A, Div, Form, Input, Button

app, rt = fast_app(secret_key="change-me")  # enables signed session cookies

@rt("/")
def get():
    return Titled("Admin", P("Welcome to choresir admin"))
```

## Common Patterns

### Authentication with Beforeware

```python
from fasthtml.common import fast_app, RedirectResponse, Beforeware

def auth_before(req, sess):
    auth = req.scope["auth"] = sess.get("admin_user", None)
    if not auth:
        return RedirectResponse("/admin/login", status_code=303)

beforeware = Beforeware(
    auth_before,
    skip=["/admin/login", "/admin/login/submit"],
)

app, rt = fast_app(before=beforeware, secret_key="change-me")
```

### Login/logout flow

```python
@rt("/login")
def get():
    return Titled("Login", Form(
        Input(name="username", placeholder="Username"),
        Input(name="password", type="password", placeholder="Password"),
        Button("Login"),
        action="/admin/login/submit", method="POST"
    ))

@rt("/login/submit")
def post(username: str, password: str, sess):
    if username == ADMIN_USER and password == ADMIN_PASSWORD:
        sess["admin_user"] = username
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin/login?error=1", status_code=303)

@rt("/logout")
def get(sess):
    sess.pop("admin_user", None)
    return RedirectResponse("/admin/login", status_code=303)
```

### Rendering HTML with FT components

```python
from fasthtml.common import Titled, Table, Tr, Th, Td, A, Div, P

@rt("/members")
async def get(auth):
    members = await member_service.list_all(session)
    rows = [Tr(Td(m.name), Td(m.role), Td(m.status)) for m in members]
    return Titled(
        "Members",
        Table(Tr(Th("Name"), Th("Role"), Th("Status")), *rows)
    )
```

### Mounting inside FastAPI

```python
from fastapi import FastAPI
from fasthtml.common import fast_app

admin_app, rt = fast_app(secret_key=settings.admin_secret)
# define routes on rt...

fastapi_app = FastAPI()
fastapi_app.mount("/admin", admin_app)
```

### Session access in handlers

```python
@rt("/profile")
def get(req, sess):
    user = sess.get("admin_user")
    visits = sess.setdefault("visits", 0) + 1
    sess["visits"] = visits
    return P(f"Hello {user}, visit #{visits}")
```

## Gotchas & Pitfalls

- **`fast_app()` returns `(app, rt)`**: `rt` is the route decorator — use `@rt("/path")` not `@app.route("/path")`.
- **`secret_key` is required for sessions**: Without it, the session cookie is not signed and provides no security. Use a strong random value from settings.
- **CSRF**: FastHTML's session-cookie model provides CSRF protection when using `secret_key`. For form submissions, ensure POST endpoints check the session for auth.
- **Beforeware `auth` injection**: The `auth` parameter in handler functions is automatically injected from `req.scope["auth"]` set by beforeware — do not try to extract it from `sess` manually.
- **`skip` patterns are regexes**: The `skip` list in `Beforeware` uses regex matching, not glob. Use raw strings: `r"/static/.*"`.
- **FastHTML uses Starlette sessions**: Sessions are signed cookies (not server-side). Avoid storing large or sensitive data; store only user IDs.

## Idiomatic Usage

Keep page handlers thin — delegate DB queries to services injected via the app factory. Use `Titled()` for consistent page layout. Build tables and lists with list comprehensions over FT component constructors rather than string templates.
