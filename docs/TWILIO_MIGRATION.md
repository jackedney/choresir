# Twilio WhatsApp Migration Guide

Migration from Meta WhatsApp Cloud API to Twilio WhatsApp API.

---

## Why Twilio?

| Benefit | Description |
|---------|-------------|
| **Simpler Setup** | No Meta business verification, app review, or complex portal navigation |
| **Unified SDK** | Same `twilio` Python package for WhatsApp, SMS, Voice |
| **Built-in Sandbox** | Test immediately without production approval |
| **Better Docs** | Comprehensive Python examples and API reference |
| **Familiar Pattern** | Form-encoded webhooks like traditional SMS |

**Trade-offs:**
- Slightly higher per-message cost (~$0.005-0.01 Twilio markup)
- Additional vendor layer between you and Meta

---

## Prerequisites

1. **Twilio Account**: Sign up at [twilio.com](https://www.twilio.com)
2. **WhatsApp Sandbox**: Enable in Twilio Console → Messaging → Try it Out → WhatsApp
3. **Connect Test Phone**: Send the join code to sandbox number (e.g., "join example-word")

---

## Environment Variable Changes

```diff
# Remove these Meta variables:
- WHATSAPP_VERIFY_TOKEN=your_random_verify_token_here
- WHATSAPP_APP_SECRET=your_app_secret_from_meta_developer_console
- WHATSAPP_ACCESS_TOKEN=your_access_token_from_meta_developer_console
- WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_from_meta_dashboard

# Add these Twilio variables:
+ TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
+ TWILIO_AUTH_TOKEN=your_auth_token_here
+ TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

Get credentials from: Twilio Console → Account → API keys & tokens

---

## Code Changes Required

### 1. Dependencies (`pyproject.toml`)

```diff
+ twilio>=9.0.0
```

### 2. Configuration (`src/core/config.py`)

```python
# Remove
whatsapp_verify_token: str
whatsapp_app_secret: str
whatsapp_access_token: str
whatsapp_phone_number_id: str

# Add
twilio_account_sid: str
twilio_auth_token: str
twilio_whatsapp_number: str  # Format: "whatsapp:+14155238886"
```

### 3. Webhook Handler (`src/interface/webhook.py`)

**Remove:** GET `/webhook` verification endpoint (Twilio doesn't need it)

**Change signature verification:**
```python
# Before (Meta)
def verify_signature(payload: bytes, signature: str) -> bool:
    computed = hmac.new(settings.whatsapp_app_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={computed}", signature)

# After (Twilio)
from twilio.request_validator import RequestValidator

def verify_signature(url: str, params: dict, signature: str) -> bool:
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, params, signature)
```

**Change request parsing:**
```python
# Before (Meta): JSON body
payload = await request.json()

# After (Twilio): Form data
form_data = await request.form()
params = dict(form_data)
```

### 4. Message Parser (`src/interface/whatsapp_parser.py`)

```python
# Before (Meta nested JSON)
message_id = payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
from_phone = payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
text = payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

# After (Twilio flat form params)
message_id = params.get("MessageSid")
from_phone = params.get("From", "").replace("whatsapp:", "")
text = params.get("Body")
profile_name = params.get("ProfileName")  # Bonus: sender's WhatsApp name
```

### 5. Message Sender (`src/interface/whatsapp_sender.py`)

```python
# Before (Meta direct HTTP)
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}}
    )

# After (Twilio SDK)
from twilio.rest import Client

client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
message = client.messages.create(
    from_=settings.twilio_whatsapp_number,
    to=f"whatsapp:{phone}",
    body=text
)
```

### 6. Template Messages (`src/interface/whatsapp_templates.py`)

Twilio uses Content API instead of Meta's template names:

1. Create templates in Twilio Console → Content Editor
2. Get Content SID (e.g., `HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
3. Send using:

```python
message = client.messages.create(
    from_=settings.twilio_whatsapp_number,
    to=f"whatsapp:{phone}",
    content_sid="HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    content_variables=json.dumps({"1": user_name, "2": chore_title})
)
```

---

## Webhook Configuration

### Local Development (ngrok)

1. Start FastAPI: `uv run fastapi run src/main.py --port 8000`
2. Start ngrok: `ngrok http 8000`
3. Configure in Twilio Console → Messaging → WhatsApp Sandbox → Webhook:
   - **When a message comes in**: `https://abc123.ngrok-free.app/webhook`
   - **Method**: POST

### Production (Railway)

Update webhook URL in Twilio Console to your Railway public URL:
- `https://choresir-api.railway.app/webhook`

---

## Testing Checklist

- [ ] Twilio sandbox connected (sent join code)
- [ ] Environment variables set
- [ ] Webhook URL configured in Twilio Console
- [ ] Send test message → webhook receives it
- [ ] Webhook returns 200 OK (check ngrok inspector)
- [ ] Outbound message sends successfully
- [ ] Template message sends (after 24h window)

---

## Rollback Plan

If issues arise, revert to Meta by:
1. Restore original environment variables
2. Revert code changes
3. Update webhook URL in Meta Developer Console

---

## Cost Comparison

| Provider | Inbound | Outbound | Template |
|----------|---------|----------|----------|
| Meta Direct | Free | $0.005-0.05/msg | $0.005-0.05/msg |
| Twilio | Free | $0.005 + Meta fee | $0.005 + Meta fee |

Twilio adds ~$0.005/message markup. For low-volume household use (~100 msgs/day), this is ~$15/month additional.

---

## References

- [Twilio WhatsApp Quickstart](https://www.twilio.com/docs/whatsapp/quickstart)
- [Twilio Python SDK](https://www.twilio.com/docs/libraries/python)
- [Webhook Security (Signature Validation)](https://www.twilio.com/docs/usage/webhooks/webhooks-security)
- [Content API for Templates](https://www.twilio.com/docs/content)
