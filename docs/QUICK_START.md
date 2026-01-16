# Quick Start Guide

Get the bot running locally and test your first message.

**Time:** 30 minutes
**Prerequisites:** Meta WhatsApp Business App, WhatsApp tokens, OpenRouter API key

## 1. Submit WhatsApp Templates (Start Now)

Approval takes 1-2 days. Submit while doing other setup.

See [WHATSAPP_TEMPLATES.md](./WHATSAPP_TEMPLATES.md) for details.

Required templates: `chore_reminder`, `verification_request`, `conflict_notification`

## 2. Setup Local Environment

```bash
# Install dependencies
uv sync

# Download PocketBase
task setup

# Configure environment
cp .env.example .env
nano .env  # Add your tokens
```

Required `.env` variables:
```bash
POCKETBASE_URL=http://127.0.0.1:8090
POCKETBASE_ADMIN_EMAIL=<your email>
POCKETBASE_ADMIN_PASSWORD=<your password>
OPENROUTER_API_KEY=<your key>
WHATSAPP_VERIFY_TOKEN=<your token>
WHATSAPP_APP_SECRET=<your secret>
WHATSAPP_ACCESS_TOKEN=<your token>
WHATSAPP_PHONE_NUMBER_ID=<your id>
HOUSE_CODE=HOUSE123
HOUSE_PASSWORD=SecretPass
```

Optional:
```bash
LOGFIRE_TOKEN=<your token>  # See LOGFIRE_SETUP.md
```

## 3. Setup ngrok

See [NGROK_SETUP.md](./NGROK_SETUP.md) for details.

```bash
brew install ngrok
ngrok config add-authtoken YOUR_TOKEN
```

## 4. Start Services

**Terminal 1: PocketBase**
```bash
./pocketbase serve
```
First time: Create admin account at http://127.0.0.1:8090/_/

**Terminal 2: FastAPI**
```bash
uv run fastapi dev src/main.py --port 8000
```

**Terminal 3: ngrok**
```bash
ngrok http 8000
```
Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

## 5. Configure WhatsApp Webhook

1. Go to [Meta Developer Console](https://developers.facebook.com)
2. Navigate to **WhatsApp** → **Configuration**
3. Edit webhook:
   - **Callback URL**: `https://abc123.ngrok-free.app/webhook`
   - **Verify Token**: (from your `.env`)
4. Subscribe to **messages** events

## 6. Create First Admin User

Send to bot:
```
Join HOUSE123 SecretPass YourName
```

Then in PocketBase admin (http://127.0.0.1:8090/_/):
1. Go to **Collections** → **users**
2. Edit your user: set `role` to "admin", `status` to "active"
3. Save

## 7. Test

**Basic message:**
```
Hello
```

**Create chore:**
```
Remind me to water plants every 3 days
```

**Log completion:**
```
I watered the plants
```

## Troubleshooting

**Webhook verification fails:**
- FastAPI running on port 8000?
- ngrok tunnel active?
- Verify token matches `.env`?

**Bot doesn't reply:**
- OpenRouter API key valid?
- WhatsApp access token valid?
- Check FastAPI logs

## Next Steps

- Add more household members
- Wait for template approval
- Deploy to Railway (see [RAILWAY_DEPLOYMENT.md](./RAILWAY_DEPLOYMENT.md))
