---
name: tech-waha
description: Reference guide for WAHA — self-hosted WhatsApp HTTP API for messaging and webhooks
user-invocable: false
---

# WAHA (WhatsApp HTTP API)

> Purpose: WhatsApp integration — receives group messages via webhooks, sends replies via REST API
> Docs: https://waha.devlike.pro / https://github.com/devlikeapro/waha
> Version researched: latest (self-hosted Docker)

## Quick Start

```yaml
# docker-compose.yml
services:
  waha:
    image: devlikeapro/waha:latest
    ports:
      - "3000:3000"
    environment:
      WHATSAPP_API_KEY: "your-api-key"
      WHATSAPP_HOOK_URL: "http://choresir:8000/webhook"
      WHATSAPP_HOOK_EVENTS: "message"
```

## Common Patterns

### Webhook payload structure (inbound)

```python
# Group message — "from" is the GROUP, "participant" is the sender
{
    "event": "message",
    "session": "default",
    "payload": {
        "id": "true_120363XXXX@g.us_ABCD1234",
        "from": "120363XXXX@g.us",          # group JID (@g.us)
        "to": "1234567890@c.us",             # bot's own JID
        "participant": "9876543210@c.us",    # actual sender JID
        "body": "Hello, can you add a task?",
        "timestamp": 1700000000,
        "fromMe": false,
        "_data": {...}
    }
}

# DM — "from" is the sender, no "participant" field
{
    "event": "message",
    "session": "default",
    "payload": {
        "id": "true_1234567890@c.us_ABCD1234",
        "from": "1234567890@c.us",           # sender JID (@c.us)
        "to": "9876543210@c.us",             # bot's own JID
        "body": "Hi there!",
        "timestamp": 1700000000,
        "fromMe": false,
        "_data": {...}
    }
}
```

### Webhook signature validation

```python
import hmac
import hashlib

def validate_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

# In FastAPI handler:
@router.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("X-WAHA-Signature-256", "")
    if not validate_webhook(body, sig, settings.waha_secret):
        raise WebhookAuthError()
    payload = json.loads(body)
    ...
```

### Sending a text message

```python
async def send_text(chat_id: str, text: str) -> None:
    await http.post(
        "/api/sendText",
        json={
            "chatId": chat_id,   # group JID: "120363XXXX@g.us"
            "text": text,
            "session": "default",
        },
        headers={"X-Api-Key": settings.waha_api_key},
    )
```

### Session management (initial setup)

```python
# Start a session (done once via admin UI or CLI)
POST /api/sessions/default/start
{}

# Check session status (returns JSON with "status" field)
GET /api/sessions/default

# QR code for authentication
GET /api/screenshot?session=default
```

### Detecting new member joins

```python
# WAHA emits "group.v2.join" event for new participants
if payload["event"] == "group.v2.join":
    for participant in payload["payload"]["participants"]:
        await member_service.register_pending(participant["id"])
```

## Gotchas & Pitfalls

- **`id` field is the dedup key**: Use `payload.id` as the primary key for the message job queue — WAHA guarantees uniqueness per message.
- **`fromMe: true` messages must be filtered**: WAHA delivers your own outbound messages back as webhooks. Filter `payload.fromMe == true` before processing.
- **Group JID format**: Group chats use `@g.us` suffix; individual chats use `@c.us`. The agent only processes group messages.
- **Group `from`/`to` swap**: In group messages, `from` is the **group JID** (not the sender) and `participant` holds the actual sender. Check `from.endswith("@g.us")` to detect group messages.
- **Session must be authenticated before webhooks flow**: If the WAHA session is not QR-authenticated, no webhooks arrive. The admin interface handles session setup.
- **Webhook events must be configured**: Set `WHATSAPP_HOOK_EVENTS=message,group.v2.join` (or equivalent) — by default WAHA may not emit all event types.
- **Rate limits from WhatsApp**: WhatsApp may throttle accounts that send too many messages. Respect outbound rate limits — do not send more than ~20 messages/minute.

## Idiomatic Usage

Treat WAHA as an external infrastructure dependency behind the `MessageSender` protocol. The `WAHAClient` implements `MessageSender`; tests use a `FakeSender`. This way, no code depends on WAHA's API directly except the single client class.
