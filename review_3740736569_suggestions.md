# Code Review Suggestions from PR #64, Review #3740736569

## Outside Diff Range Comments

### src/core/recurrence_parser.py

**Reject non-positive intervals to prevent invalid schedules.** (Lines 18-23, 38-41)
- Severity: 🔴 Major
- `every 0 days` currently yields `INTERVAL:0:...`, which is likely invalid or creates pathological scheduling.
- Guard against `days <= 0` and raise a `ValueError`.

**Proposed fix:**
```diff
      if match:
          days = int(match.group(1))
+        if days <= 0:
+            raise ValueError("Interval must be at least 1 day")
          # Encode interval in CRON string: INTERVAL:N:cron_expression
          # This allows us to add N days programmatically instead of using invalid CRON syntax
          return f"INTERVAL:{days}:0 0 * * *"
```

---

**Normalize input before `croniter.is_valid()` to avoid false negatives and ensure consistency.** (Lines 11-18)
- Severity: 🟡 Minor
- `parse_recurrence_to_cron` (lines 14 and 18) and `parse_recurrence_for_personal_chore` (line 34) do not strip whitespace before validation or regex matching.
- This causes leading/trailing whitespace to fail CRON validation or prevent pattern matching.
- Additionally, `parse_recurrence_for_personal_chore` creates a stripped version on line 31 but validates the unstripped input on line 34, creating inconsistency.

**Proposed fix:**
```diff
  `@functools.cache`
  def parse_recurrence_to_cron(recurrence: str) -> str:
      """Parse recurrence string to CRON expression or INTERVAL:N:cron format."""
+    recurrence_stripped = recurrence.strip()
      # Check if already a valid CRON expression
-    if croniter.is_valid(recurrence):
-        return recurrence
+    if croniter.is_valid(recurrence_stripped):
+        return recurrence_stripped
@@
-    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence.lower())
+    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence_stripped.lower())
@@
  def parse_recurrence_for_personal_chore(recurrence: str) -> tuple[str | None, datetime | None]:
      """Parse recurrence string for personal chores supporting CRON, interval, or natural language formats."""
-    recurrence_lower = recurrence.lower().strip()
+    recurrence_stripped = recurrence.strip()
+    recurrence_lower = recurrence_stripped.lower()
@@
-    if croniter.is_valid(recurrence):
-        return (recurrence, None)
+    if croniter.is_valid(recurrence_stripped):
+        return (recurrence_stripped, None)
```

---

### src/interface/webhook.py

**Avoid logging phone numbers in admin notifications.** (Lines 446-456)
- Severity: 🔴 Major
- Line 448 assigns `parsed_message.from_phone` to `user_context`, which is then included in the admin notification message at line 456.
- Phone numbers are PII and should not be logged or included in notifications.

**Proposed fix:**
```diff
              user_context = "Unknown user"
              if parsed_message and parsed_message.from_phone:
-                user_context = parsed_message.from_phone
+                # Use message_id as context instead of phone number (PII)
+                user_context = f"message_id: {parsed_message.message_id}"

              timestamp = datetime.now().isoformat()
```

---

### tests/unit/test_whatsapp_sender.py

**Add explicit type hints to the fixture and patched test parameters.** (Lines 3-19)
- Severity: 🟡 Minor
- The fixture `mock_asyncio_sleep()` at line 16 and the mock parameters at lines 172 and 186 are missing type annotations, violating the strict typing requirement.

**Proposed update:**
```diff
-from unittest.mock import AsyncMock, MagicMock, patch
+from collections.abc import Generator
+from unittest.mock import AsyncMock, MagicMock, patch

 `@pytest.fixture`(autouse=True)
-def mock_asyncio_sleep():
+def mock_asyncio_sleep() -> Generator[AsyncMock, None, None]:

-    async def test_send_text_message_rate_limited(self, mock_rate_limiter) -> None:
+    async def test_send_text_message_rate_limited(self, mock_rate_limiter: MagicMock) -> None:

-    async def test_rate_limiter_records_request(self, mock_rate_limiter) -> None:
+    async def test_rate_limiter_records_request(self, mock_rate_limiter: MagicMock) -> None:
```

Additionally, consider using a constant from `src.interface.whatsapp_sender` instead of hardcoding `60` at lines 47 and 60.

---

## Fix All Issues with AI Agents

### src/interface/whatsapp_sender.py

**Remove unreachable code at end of send_wa_message.** (Lines 174-175)
- The final `logger.error` and `return` in send loop are unreachable in `send_wa_message` (they're covered by returns on success, 4xx client errors, and retry-exhaustion in the except blocks).
- Remove the two lines (`logger.error(...)`, `return SendMessageResult(...)`) from the end of the function.
- Alternatively, if you prefer a defensive fallback, keep them but add a clear comment stating they are unreachable and exist only as a safety net.

---

## Nitpick Comments

### src/core/recurrence_parser.py

**Bound the cache to avoid unbounded growth on user input.** (Lines 10-11)
- `functools.cache` is unbounded; if this function is called with many distinct strings (e.g., user-generated), memory can grow without limit.
- Prefer a bounded `lru_cache`.

**Proposed change:**
```diff
-@functools.cache
+@functools.lru_cache(maxsize=256)
 def parse_recurrence_to_cron(recurrence: str) -> str:
```

---

### src/interface/whatsapp_sender.py

**Consider using `@functools.lru_cache(maxsize=...)` instead of unbounded `@functools.cache`.** (Lines 72-80)
- `@functools.cache` stores entries indefinitely.
- If the application processes many unique phone numbers over time, this could lead to memory growth.
- Consider using `@functools.lru_cache(maxsize=1024)` or similar to bound the cache size.

**Proposed change:**
```diff
-@functools.cache
+@functools.lru_cache(maxsize=1024)
 def format_phone_for_waha(phone: str) -> str:
```

---

### src/services/personal_verification_service.py

**Inconsistent logging style: f-strings vs structured logging.** (Lines 277, 295, 305)
- Lines 277, 295, and 305 use f-string interpolation while most other logs in this file use structured logging with `extra`.
- For consistency, consider using structured logging throughout, though the current implementation is functionally correct and doesn't log PII.

**Proposed change for line 277:**
```diff
-                logger.info(f"Auto-verified personal chore log {log['id']} (48h timeout)")
+                logger.info(
+                    "Auto-verified personal chore log (48h timeout)",
+                    extra={"log_id": log["id"]},
+                )
```

---

### src/interface/webhook.py

**Consider narrowing the exception catch for admin notification failures.** (Lines 462-463)
- The broad `except Exception` could mask unexpected errors.
- Consider catching specific expected exceptions like `(RuntimeError, ConnectionError, OSError)` to match the pattern used elsewhere in this PR.

**Proposed change:**
```diff
-        except Exception:
+        except (RuntimeError, ConnectionError, OSError):
             logger.exception("Failed to notify admins of critical error")
```

---

### src/core/config.py

**Consider documenting the `type: ignore` rationale.** (Lines 169-171)
- The `# type: ignore[arg-type]` suppresses a type checker warning that occurs because `Settings()` can raise `ValidationError` if required fields (like `waha_webhook_hmac_key`) are missing.
- While the suppression is necessary here since the function signature promises to return `Settings`, a brief inline comment explaining why would aid future maintainers.

**Suggested clarification:**
```diff
 def get_settings() -> Settings:
     """Get application settings (singleton pattern)."""
-    return Settings()  # type: ignore[arg-type]
+    # type: ignore needed because Settings() may raise ValidationError for missing required fields
+    return Settings()  # type: ignore[arg-type]
```

---

### src/services/conflict_service.py

**Inconsistent logging style: f-strings vs structured logging.** (Lines 275, 281, 287)
- Lines 275, 281, and 287 use f-strings for log messages while other parts of this file (Lines 84-91, 186-188, 205) use structured logging with the `extra` parameter.
- For consistency and better log aggregation, consider using structured logging here as well.

**Suggested refactor for consistency:**
```diff
-            logger.info(f"Vote result: APPROVED - chore {chore_id} completed")
+            logger.info("Vote result: APPROVED - chore completed", extra={"chore_id": chore_id, "result": "approved"})

-            logger.info(f"Vote result: REJECTED - chore {chore_id} reset to TODO")
+            logger.info("Vote result: REJECTED - chore reset to TODO", extra={"chore_id": chore_id, "result": "rejected"})

-            logger.warning(f"Vote result: DEADLOCK - chore {chore_id} in deadlock state")
+            logger.warning("Vote result: DEADLOCK - chore in deadlock state", extra={"chore_id": chore_id, "result": "deadlock"})
```

---

### src/services/notification_service.py

**f-string logging is acceptable but inconsistent.** (Lines 49, 57, 98)
- These error logs use f-strings while success logs use structured logging with `extra`.
- For consistency across the codebase, consider using the `extra` parameter for these error logs as well.

---

### tests/unit/test_config.py

**Note: Duplicate assertion on lines 17 and 21.** (Lines 11-21)
- Lines 15-17 and 19-21 appear to test the same thing twice.
- If this was intentional (e.g., testing idempotency), a comment would clarify; otherwise, the duplication can be removed.

**Remove duplicate assertion:**
```diff
 def test_require_credential_with_valid_value() -> None:
     """Test require_credential returns value when credential is set."""
     settings = Settings(house_code="TEST123", house_password="secret", waha_webhook_hmac_key="test123")

     result = settings.require_credential("house_code", "House code")

     assert result == "TEST123"
-
-    result = settings.require_credential("house_code", "House code")
-
-    assert result == "TEST123"
```

---

### tests/unit/test_whatsapp_sender.py

**Avoid hard-coding the rate limit in tests.** (Lines 25-67)
- Using a shared constant keeps tests aligned if the limit changes.

**Proposed refactor:**
```diff
+from src.interface import constants
@@
-        for _ in range(60):
+        for _ in range(constants.MAX_REQUESTS_PER_MINUTE):
             limiter.record_request(phone)
@@
-        for _ in range(60):
+        for _ in range(constants.MAX_REQUESTS_PER_MINUTE):
             limiter.record_request(phone1)
```

---

### tests/unit/test_webhook.py

**Reduce patch-injected positional params to meet the keyword-only guideline.** (Lines 21-145, 262-308, 342-345)
- Consider moving patches into context managers or fixtures so test signatures stay ≤2 parameters (or can safely use `*`).

**As per coding guidelines:** Enforce keyword-only arguments with `*` for functions with more than 2 parameters.

---

**Avoid mocking DB logic in these tests.** (Lines 221-333, 338-377)
- These tests exercise DB interactions; per guidelines, use an ephemeral PocketBase instance instead of mocking `db_client`.

**As per coding guidelines:** Use pytest with ephemeral PocketBase instance for integration testing, do not mock database logic.

---

### tests/unit/test_webhook_rate_limiting.py

**Prefer an ephemeral PocketBase instance over DB mocks here.** (Lines 99-189)
- These tests validate DB-related flow; per guidelines, avoid mocking database logic.

**As per coding guidelines:** Use pytest with ephemeral PocketBase instance for integration testing, do not mock database logic.
