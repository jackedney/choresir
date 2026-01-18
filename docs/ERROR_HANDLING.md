# Error Handling Guide

This guide explains how choresir handles errors, particularly those from external services like OpenRouter AI API.

## Overview

The error handling system provides:
- **Intelligent Classification:** Automatically categorizes errors by type
- **User-Friendly Messages:** Translates technical errors into actionable user guidance
- **Admin Notifications:** Alerts admins for critical issues requiring intervention
- **Rate Limiting:** Prevents notification spam
- **Graceful Degradation:** System continues operating even when notifications fail

## Error Categories

### 1. Service Quota Exceeded
**Trigger:** OpenRouter API credits exhausted or quota limits reached

**Example Error Messages:**
- "quota exceeded"
- "insufficient credits"
- "credit limit"
- "out of credits"

**User Message:**
> "The AI service quota has been exceeded. Please try again later or contact support."

**Admin Notification:** ✅ Yes (Critical)
- Sent immediately when detected
- Rate limited to prevent spam (60-minute cooldown by default)
- Includes affected user details and timestamp

**Resolution:**
1. Check OpenRouter account credits at https://openrouter.ai/credits
2. Add more credits or wait for quota reset
3. Consider upgrading account tier if recurring

---

### 2. Rate Limit Exceeded
**Trigger:** Too many requests sent to OpenRouter in a short time window

**Example Error Messages:**
- "rate limit exceeded"
- "too many requests"
- "HTTP 429"
- "throttled"

**User Message:**
> "Too many requests. Please wait a moment and try again."

**Admin Notification:** ❌ No (Transient issue)

**Resolution:**
- User should wait 30-60 seconds before retrying
- System automatically respects rate limits
- If persistent, may indicate unusually high traffic

---

### 3. Authentication Failed
**Trigger:** Invalid or missing API credentials

**Example Error Messages:**
- "authentication failed"
- "invalid api key"
- "unauthorized"
- "HTTP 401"

**User Message:**
> "Service authentication failed. Please contact support."

**Admin Notification:** ✅ Yes (Critical)
- Indicates configuration issue
- Requires immediate attention

**Resolution:**
1. Verify `OPENROUTER_API_KEY` is set correctly in environment
2. Check API key hasn't been revoked or expired
3. Verify key has proper permissions
4. Restart service after updating credentials

---

### 4. Network Error
**Trigger:** Connection issues, timeouts, or service unavailability

**Example Error Messages:**
- "connection error"
- "timeout"
- "HTTP 502, 503, 504"
- "service unavailable"

**User Message:**
> "Network error occurred. Please check your connection and try again."

**Admin Notification:** ❌ No (Usually transient)

**Resolution:**
- Check internet connectivity
- Verify OpenRouter service status at https://openrouter.ai/status
- If persistent, may indicate infrastructure issues
- Users should retry in a few minutes

---

### 5. Unknown Error
**Trigger:** Unexpected errors not matching other categories

**User Message:**
> "An unexpected error occurred. Please try again later."

**Admin Notification:** ❌ No

**Resolution:**
- Check application logs for details
- If recurring, file a bug report with full error details
- May indicate code bug or unexpected API change

## Admin Notification System

### How It Works

1. **Error Detection:** Agent execution failures are caught in `choresir_agent.py`
2. **Classification:** Error is passed to `classify_agent_error()` in `src/core/errors.py`
3. **Notification Decision:** `should_notify_admins()` determines if error is critical
4. **Rate Limiting Check:** `NotificationRateLimiter` prevents duplicate notifications
5. **Admin Lookup:** System queries database for all active admin users
6. **Delivery:** WhatsApp message sent to each admin via `notify_admins()`

### Notification Format

```
[SEVERITY] Error message

Example:
[CRITICAL] ⚠️ OpenRouter quota exceeded. User Bob Smith (+1234567890) affected at 2026-01-18T14:30:00
```

### Rate Limiting

**Purpose:** Prevent admin notification spam during widespread outages

**Behavior:**
- First notification for an error category is always sent
- Subsequent notifications for same category are blocked for cooldown period
- Different error categories have independent rate limits
- Cooldown resets after configured time period (default: 60 minutes)

**Example:**
```
14:00 - Quota exceeded → Admin notified ✅
14:15 - Quota exceeded → Blocked (same category within 60 min) ❌
14:30 - Auth failed → Admin notified ✅ (different category)
15:01 - Quota exceeded → Admin notified ✅ (cooldown expired)
```

### Configuration

**Enable/Disable Admin Notifications:**
```bash
# In .env file
ENABLE_ADMIN_NOTIFICATIONS=true  # or false
```

**Cooldown Period:**
```bash
# In .env file
ADMIN_NOTIFICATION_COOLDOWN_MINUTES=60  # minutes between notifications per category
```

**Settings in Code:**
```python
from src.core.config import settings

# Check if notifications are enabled
if settings.enable_admin_notifications:
    # Notifications will be sent

# Get cooldown period
cooldown = settings.admin_notification_cooldown_minutes
```

## Troubleshooting Common Errors

### "The AI service quota has been exceeded"

**What happened:** OpenRouter account has run out of credits

**User Action:**
- Wait and try again later (admin will be notified)
- Contact household admin if issue persists

**Admin Action:**
1. Check OpenRouter dashboard: https://openrouter.ai/credits
2. Add more credits to account
3. Consider setting up billing alerts to prevent future outages
4. Review usage patterns to estimate monthly costs

### "Too many requests"

**What happened:** Rate limit reached due to high request volume

**User Action:**
- Wait 30-60 seconds and retry
- Avoid sending multiple messages in quick succession

**Admin Action:**
- If persistent, review request patterns in Logfire
- Consider implementing user-level rate limiting
- May indicate abuse or bot activity

### "Service authentication failed"

**What happened:** API key is invalid, missing, or revoked

**User Action:**
- Contact admin immediately
- All users will be affected until resolved

**Admin Action:**
1. Verify `OPENROUTER_API_KEY` in production environment:
   ```bash
   # On Railway or your hosting platform
   echo $OPENROUTER_API_KEY
   ```
2. If missing/invalid, update it:
   - Get new key from https://openrouter.ai/keys
   - Update environment variable in hosting platform
   - Restart application
3. Verify key permissions and quotas

### "Network error occurred"

**What happened:** Connection to OpenRouter failed

**User Action:**
- Check your internet connection
- Retry in a few minutes

**Admin Action:**
1. Check OpenRouter service status: https://openrouter.ai/status
2. Verify production server connectivity
3. Check logs for patterns (DNS issues, timeouts, etc.)
4. If widespread, consider posting status update to users

## Error Flow Diagram

```
User Message
    ↓
Agent Execution (choresir_agent.py)
    ↓
Exception Raised
    ↓
classify_agent_error() ← Determines error category
    ↓
┌─────────────┴─────────────┐
│                            │
User receives               Should notify admins?
friendly message            ↓
                           YES → notify_admins()
                                  ↓
                           Rate limiter check
                                  ↓
                           Lookup admin users
                                  ↓
                           Send WhatsApp messages
```

## Implementation Details

### Key Files

- **`src/core/errors.py`**
  - `ErrorCategory` enum defining all error types
  - `classify_agent_error()` function for error classification

- **`src/core/admin_notifier.py`**
  - `NotificationRateLimiter` class for spam prevention
  - `should_notify_admins()` determining notification triggers
  - `notify_admins()` for sending WhatsApp alerts

- **`src/agents/choresir_agent.py`**
  - `run_agent()` with try/except for error handling
  - Integration with classification and notification systems

### Error Classification Logic

Errors are matched using keyword detection (case-insensitive):

1. **Quota Exceeded:** "quota exceeded", "insufficient credits", "credit limit"
2. **Rate Limit:** "rate limit", "too many requests", "429", "throttled"
3. **Authentication:** "authentication failed", "invalid api key", "unauthorized", "401"
4. **Network:** "connection", "timeout", "503", "502", "504"
5. **Unknown:** Anything not matching above patterns

**Priority:** Checked in order above; first match wins

### Testing

Comprehensive test coverage in:
- **`tests/unit/test_errors.py`** - Error classification unit tests
- **`tests/unit/test_admin_notifier.py`** - Admin notification unit tests
- **`tests/integration/test_openrouter_errors.py`** - Full error flow integration tests

Run tests:
```bash
# All error handling tests
pytest tests/unit/test_errors.py tests/unit/test_admin_notifier.py tests/integration/test_openrouter_errors.py -v

# Integration tests only
pytest tests/integration/test_openrouter_errors.py -v
```

## Monitoring and Observability

### Logfire Integration

All errors are logged to Pydantic Logfire with structured data:

```python
logfire.error(
    "Agent execution failed",
    error=str(e),
    error_category=error_category.value,
)
```

**View in Logfire:**
1. Filter by error category: `error_category = "service_quota_exceeded"`
2. Check error frequency over time
3. Correlate with user activity patterns
4. Set up alerts for critical error spikes

### Recommended Alerts

Set up Logfire alerts for:
- **Quota Exceeded:** Alert when count > 5 in 5 minutes
- **Authentication Failed:** Alert immediately (indicates critical config issue)
- **Unknown Errors:** Alert when same error occurs > 10 times

## Best Practices

### For Users
1. **Wait before retrying** - Give the system time to recover
2. **Contact admin for persistent issues** - Don't suffer in silence
3. **Provide context** - Mention what you were trying to do when error occurred

### For Admins
1. **Monitor credit balance** - Set up alerts before running out
2. **Review error logs regularly** - Catch patterns early
3. **Keep API keys secure** - Rotate periodically, never commit to git
4. **Test in development** - Verify error handling works as expected
5. **Document incidents** - Track resolutions for future reference

### For Developers
1. **Never expose technical details to users** - Keep messages friendly and actionable
2. **Log full error details** - Critical for debugging
3. **Test all error paths** - Don't just test happy path
4. **Handle notification failures gracefully** - User experience shouldn't degrade
5. **Keep error messages consistent** - Users should recognize patterns

## Future Enhancements

Potential improvements to consider:

- [ ] **Database persistence for rate limiter** - Survive service restarts
- [ ] **Error dashboard** - Admin UI showing error trends
- [ ] **Automatic retry logic** - For transient failures
- [ ] **Circuit breaker pattern** - Prevent cascading failures
- [ ] **User-specific rate limiting** - Prevent individual user abuse
- [ ] **Email notifications** - Fallback when WhatsApp fails
- [ ] **Error recovery suggestions** - More specific guidance per error
- [ ] **Historical error tracking** - Trend analysis and reporting
