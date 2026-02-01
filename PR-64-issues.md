## PR #64 Issues to Fix

### Critical (Security)

- [ ] **Add HMAC webhook validation** (`src/interface/webhook.py`)
  - Twilio signature verification was removed but no WAHA equivalent added
  - WAHA supports `X-Webhook-Hmac` header (SHA512) for authentication
  - Without this, anyone can forge webhook payloads
  - Add config option `WAHA_WEBHOOK_HMAC_KEY` and validate against raw request body

### Important

- [ ] **Handle missing timestamp in parser** (`src/interface/whatsapp_parser.py:69-72`)
  - `str(payload.get("timestamp", ""))` returns empty string when missing
  - Causes `int("")` ValueError in `validate_webhook_timestamp()`
  - Use `datetime.now().timestamp()` as fallback or raise explicit error

- [ ] **Add logging to sender module** (`src/interface/whatsapp_sender.py`)
  - Missing `import logging` and `logger = logging.getLogger(__name__)`
  - Send failures not logged for debugging

- [ ] **Remove PII from logs** (`src/services/notification_service.py:139`)
  - `logger.debug("Sending text verification message to %s", to_phone)` logs phone numbers
  - Replace with: `logger.debug("Sending text verification message", extra={"operation": "verification_message_send"})`

### Minor

- [ ] **Add return type hints to tests** (`tests/unit/test_whatsapp_sender.py:70-84`)
  - Test methods in `TestFormatPhoneForWaha` missing `-> None` annotations

- [ ] **Avoid redundant parsing** (`src/interface/webhook.py:435,456`)
  - `parse_waha_webhook(params)` called twice in `_handle_webhook_error`
  - Parse once at start and reuse result
