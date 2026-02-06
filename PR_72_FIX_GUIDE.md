# PR #72 Review Fix Guide

This document provides a prioritized guide for addressing all review comments from PR #72.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 Critical | 2 | Must fix - breaks functionality or security |
| 🟠 Major | 8 | Should fix - significant issues |
| 🟡 Minor | 17 | Nice to fix - code quality improvements |
| 🧹 Nitpick | 11 | Optional - style/preference |

---

## 🔴 Critical Issues (Must Fix)

### 1. Invalid `ClientResponseError` Import
**File:** `src/core/schema.py:8`

**Problem:** The import `from pocketbase.errors import ClientResponseError` does not exist in the vaphes/pocketbase Python SDK (v0.13+). This will cause a runtime `ImportError`.

**Fix:**
```python
# Remove line 8:
# from pocketbase.errors import ClientResponseError

# Add httpx import if not present:
import httpx

# Replace any `except ClientResponseError` blocks with:
except httpx.HTTPStatusError as e:
    # Handle HTTP errors
except httpx.RequestError as e:
    # Handle connection/timeout errors
```

Also check `src/core/db_client.py` line 530 where `ClientResponseError` may be used.

---

### 2. Phone-based DOM IDs Break HTMX Selectors
**Files:**
- `templates/admin/member_row.html`
- `templates/admin/edit_member_inline.html`
- `templates/admin/remove_member_inline.html`
- `templates/admin/members.html`

**Problem:** Phone numbers like `+14155552671` create invalid CSS selectors (`#member-+14155552671`) because `+` is a CSS combinator. HTMX swaps will fail silently.

**Fix:** Replace `member.phone` with `member.id` in all DOM IDs and `hx-target` attributes:

```html
<!-- Before -->
<tr id="member-{{ member.phone }}">
<button hx-target="#member-{{ member.phone }}">

<!-- After -->
<tr id="member-{{ member.id }}">
<button hx-target="#member-{{ member.id }}">
```

Apply to all 4 template files.

---

## 🟠 Major Issues (Should Fix)

### 3. Admin Session Cookie Not Secure in Production
**File:** `src/interface/admin_router.py:136-142`

**Problem:** `secure=False` exposes session cookies over HTTP, making them vulnerable to interception in production.

**Fix:**
```python
# Add to settings (e.g., src/core/settings.py):
is_production: bool = os.getenv("ENVIRONMENT", "development") == "production"

# Update cookie setting:
response.set_cookie(
    key="admin_session",
    value=session_token,
    httponly=True,
    secure=settings.is_production,  # Dynamic based on environment
    samesite="strict",
    max_age=86400,
)
```

---

### 4. Password Overwritten with Masked Placeholder
**File:** `src/interface/admin_router.py:239-248`

**Problem:** If user submits the form without changing password, `"********"` (MASKED_TEXT_PLACEHOLDER) gets saved as the actual password.

**Fix:**
```python
async def post_house_config(...):
    # ... get form data ...

    config = await get_first_record(collection="house_config", filter_query="")

    # Preserve existing password if placeholder submitted
    if config and password == MASKED_TEXT_PLACEHOLDER:
        password = config["password"]

    errors = []
    # ... validation continues ...
```

---

### 5. WhatsApp Send Failures Leave Orphaned Records
**File:** `src/interface/admin_router.py:403-414`

**Problem:** Creates user record, then creates pending invite even if WhatsApp message fails. Leaves orphaned pending users.

**Fix:**
```python
# Import delete_record
from src.core.db_client import (
    create_record,
    delete_record,  # Add this
    get_first_record,
    ...
)

# In post_add_member:
created_user = await create_record(collection="users", data=user_data)
logger.info("Created pending user: %s", phone)

send_result = await send_text_message(to_phone=phone, text=invite_message)

if not send_result.success:
    # Rollback user creation
    await delete_record(collection="users", record_id=created_user["id"])
    return templates.TemplateResponse(
        request,
        name="admin/add_member.html",
        context={"errors": [send_result.error or "Failed to send invite"], "phone": phone},
    )

# Only create invite after successful send
await create_record(collection="pending_invites", data=invite_data)
```

---

### 6. Empty Credentials Bypass in Validation
**File:** `src/services/house_config_service.py:53-56`

**Problem:** `secrets.compare_digest` called against empty strings when config is unset, potentially allowing empty credentials to pass.

**Fix:**
```python
async def validate_house_credentials(house_code: str, password: str) -> bool:
    """Validate house code and password against stored config."""
    config = await get_house_config()

    # Guard against empty config values
    if not config.get("code") or not config.get("password"):
        return False

    house_code_valid = secrets.compare_digest(house_code, config["code"])
    password_valid = secrets.compare_digest(password, config["password"])
    return house_code_valid and password_valid
```

---

### 7. Missing CSRF Token in Remove Member Form
**File:** `templates/admin/remove_member.html:56-61`

**Problem:** POST form lacks CSRF protection, vulnerable to cross-site request forgery.

**Fix:**
```html
<form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
    <div role="group">
        <button type="submit" data-theme="danger">Ban Member</button>
        <a href="/admin/members" role="button" class="secondary">Cancel</a>
    </div>
</form>
```

Also requires backend changes to:
1. Generate CSRF tokens
2. Pass them to templates
3. Validate on POST handlers

---

### 8. Raw Dicts Instead of Pydantic DTOs
**Files:**
- `src/interface/admin_router.py:390, 408, 246`
- `src/services/user_service.py`

**Problem:** Using raw dicts for user, invite, and house config creation instead of typed Pydantic models.

**Fix:** Create DTOs in `src/domain/`:
```python
# src/domain/create_models.py
from pydantic import BaseModel

class UserCreate(BaseModel):
    phone: str
    name: str
    status: str = "pending"
    role: str = "member"

class InviteCreate(BaseModel):
    phone: str
    invite_message_id: str

class HouseConfigCreate(BaseModel):
    name: str
    password: str
    code: str
```

Update usages:
```python
# Before
user_data = {"phone": phone, "name": name, "status": "pending", "role": "member"}

# After
user_data = UserCreate(phone=phone, name=name).model_dump()
```

---

### 9. Docstrings Not Minimal (Single-Line)
**File:** `src/services/house_config_service.py:14-35`

**Problem:** Multi-line docstrings with Args/Returns sections violate coding guidelines.

**Fix:** Replace with single-line docstrings:
```python
# Before
async def get_house_config() -> dict[str, Any]:
    """Get house configuration.

    Returns:
        dict[str, Any]: House configuration with name, password, code.

    Note:
        Falls back to environment variables if no DB config.
    """

# After
async def get_house_config() -> dict[str, Any]:
    """Get house configuration from DB or environment fallback."""
```

---

### 10. Tests Use Mocks Instead of Ephemeral PocketBase
**File:** `tests/unit/test_choresir_agent.py:305-409`

**Problem:** Tests mock `db_client` and services instead of using real PocketBase integration fixture.

**Fix:** Convert to integration tests:
```python
@pytest.mark.asyncio
async def test_yes_confirms_invite(pb_client):  # Use fixture
    """Test confirming a pending invite."""
    # Create real records
    user = await pb_client.collection("users").create({
        "phone": "+1234567890",
        "name": "Test User",
        "status": "pending"
    })
    await pb_client.collection("pending_invites").create({
        "phone": "+1234567890",
        "invite_message_id": "msg123"
    })
    await pb_client.collection("house_config").create({
        "name": "Test House",
        "password": "testpass",
        "code": "1234"
    })

    # Call actual function
    result = await handle_unknown_user("+1234567890", "yes")

    # Assert real state changes
    updated_user = await pb_client.collection("users").get_one(user.id)
    assert updated_user.status == "active"
    assert "Welcome" in result
```

---

## 🟡 Minor Issues (Nice to Fix)

### 11. Missing CSRF Token in Login Form
**File:** `templates/admin/login.html:19-26`

Add CSRF token input similar to remove_member form.

---

### 12. Password Field Has `required` But Should Allow Empty
**File:** `templates/admin/house.html:32-35`

**Fix:** Remove `required` attribute since placeholder says "enter new password to change":
```html
<input type="password" id="password" name="password" placeholder="Enter new password to change" />
```

---

### 13. Documentation Still References Old Join Command
**File:** `docs/index.md:16`

**Fix:**
```markdown
<!-- Before -->
| Join household | `/house join MyHouse` | Starts onboarding flow |

<!-- After -->
| Join household | Reply YES to an admin invite | Admin-managed invites |
```

---

### 14. Missing `hx-indicator` Attribute
**File:** `templates/admin/edit_member_inline.html:4-31`

**Fix:**
```html
<form hx-post="..." hx-target="..." hx-swap="outerHTML" hx-indicator="#member-{{ user.phone }}-saving">
...
<span id="member-{{ user.phone }}-saving" class="htmx-indicator">Saving...</span>
```

---

### 15. Mock Fixtures Should Use Pydantic Models
**File:** `tests/unit/test_choresir_agent.py:280-299`

Use `User` model from `src/domain/user.py` instead of raw dicts.

---

### 16. Typo in Comment
**File:** `src/core/scheduler.py:578-579`

**Fix:**
```python
# Before: # Call) auto-verification service
# After:  # Call auto-verification service
```

---

### 17. Skipped Test Has Inconsistent Setup
**File:** `tests/unit/test_house_config.py:85-111`

Remove the session cookie setup from the skipped test since it tests unauthenticated access.

---

### 18. Markdown Code Blocks Missing Language Identifier
**File:** `docs/architecture.md:5-41, 45-60`

**Fix:**
~~~markdown
```text
┌─────────────────────────────────────────────────────────────────┐
...
```
~~~

---

### 19. Phone Numbers in URLs Need Encoding
**File:** `templates/admin/members.html:48-49`

**Fix:**
```html
<button hx-get="/admin/members/{{ member.phone | urlencode }}/edit" ...>
```

---

### 20. Use Double Quotes for String Literals
**File:** `src/interface/admin_router.py:303-306`

**Fix:**
```python
# Before
filter_query=f'phone = "{sanitize_param(phone)}"'

# After
filter_query=f"phone = \"{sanitize_param(phone)}\""
```

---

### 21. Add Structured Context to Logs
**Files:**
- `src/interface/admin_router.py:401, 414`
- `src/agents/choresir_agent.py:272, 286`

**Fix:**
```python
# Before
logger.info("Created pending user: %s", phone)

# After
logger.info("created_pending_user", extra={"phone": phone})
```

---

### 22. Return Updated Data in HTMX Response
**File:** `src/interface/admin_router.py:528-540`

**Fix:**
```python
updated_user = await update_record(
    collection="users",
    record_id=user["id"],
    data={"name": name.strip(), "role": role},
)

return templates.TemplateResponse(
    request,
    name="admin/member_row.html",
    context={"member": updated_user},  # Use updated data
)
```

---

### 23. Mock `sanitize_param` in Tests
**File:** `tests/unit/test_handle_unknown_user.py:17-28`

**Fix:**
```python
with (
    patch("src.agents.choresir_agent.db_client") as mock_db_client,
    ...
):
    mock_db_client.sanitize_param = lambda x: x  # Pass through
```

---

### 24. Condense Docstrings in admin_router
**File:** `src/interface/admin_router.py:30-40`

Convert multi-line docstrings to single-line.

---

### 25. User Model docstring outdated
**File:** `src/services/user_service.py:17-43`

Update docstring to reflect that validation now uses database config, not just environment variables.

---

### 26. Cookie clearing assertion could be more robust
**File:** `tests/unit/test_admin_login.py:153-156`

**Fix:**
```python
assert 'admin_session=""' in set_cookie or "max-age=0" in set_cookie.lower()
```

---

### 27. Test name doesn't match behavior
**File:** `tests/unit/test_pending_invites.py:82-95`

Rename `test_create_duplicate_phone_updates_existing` to `test_create_duplicate_phone_in_memory_db`.

---

## 🧹 Nitpick Issues (Optional)

### 28. Duplicate `.gitignore` Entry
**File:** `.gitignore:71-72`

Remove duplicate `pb_migrations/` entry (already on line 48).

---

### 29. Add SRI Hashes for CDN Resources
**File:** `templates/admin/base.html:7-8`

```html
<link rel="stylesheet" href="..." integrity="sha384-..." crossorigin="anonymous">
<script src="..." integrity="sha384-..." crossorigin="anonymous"></script>
```

---

### 30. Logout Link Visible on Login Page
**File:** `templates/admin/base.html:33-42`

Add conditional block around navigation or override in login.html.

---

### 31. Inconsistent Terminology: "Remove" vs "Ban"
**File:** `templates/admin/remove_member.html:3, 19`

Align page title with heading/button text (choose "Remove" or "Ban" consistently).

---

### 32. Consider Hashing Shared House Password
**File:** `src/core/schema.py:318-333`

Security consideration: house_config stores password as plaintext. Consider if hashing is warranted.

---

### 33. Move mkdocs to Dev Dependencies
**File:** `pyproject.toml:19-20`

Move `mkdocs` and `mkdocs-material` to `[project.optional-dependencies] dev`.

---

### 34. Consider Ephemeral PocketBase for Some Unit Tests
**File:** `tests/unit/test_house_config.py:27-48`

Consider migrating to integration pattern or documenting intent as unit-only.

---

### 35. Use `pytest.mark.parametrize` for Case Variations
**File:** `tests/unit/test_handle_unknown_user.py:53-92`

```python
@pytest.mark.parametrize("message_text", ["yes", "Yes", "YES", "yEs"])
async def test_pending_invite_confirmation_case_insensitive(message_text: str):
    ...
```

---

## Implementation Order

Recommended order of fixing:

1. **Critical** (blocks runtime):
   - Fix `ClientResponseError` import (#1)
   - Fix phone-based DOM IDs (#2)

2. **Security** (production safety):
   - Secure cookie flag (#3)
   - CSRF tokens (#7, #11)
   - Empty credentials guard (#6)

3. **Data Integrity**:
   - Password masking fix (#4)
   - WhatsApp rollback (#5)

4. **Code Quality**:
   - Pydantic DTOs (#8)
   - Single-line docstrings (#9)
   - Structured logging (#21)

5. **Tests**:
   - Convert to integration tests (#10)
   - Fix test fixtures (#15, #17)

6. **Documentation & Style**:
   - Remaining minor/nitpick items
