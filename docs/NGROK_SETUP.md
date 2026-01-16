# ngrok Setup Guide

ngrok creates a secure tunnel from a public HTTPS URL to your local development server for testing WhatsApp webhooks.

## Install

**macOS:**
```bash
brew install ngrok
```

**Manual:**
```bash
curl -o ngrok.zip https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip
unzip ngrok.zip
sudo mv ngrok /usr/local/bin/
```

## Configure

1. Create account at [ngrok.com](https://ngrok.com)
2. Get auth token from dashboard
3. Configure:
```bash
ngrok config add-authtoken YOUR_TOKEN_HERE
```

## Usage

Start three terminals:

**Terminal 1: PocketBase**
```bash
./pocketbase serve
```

**Terminal 2: FastAPI**
```bash
uv run fastapi dev src/main.py --port 8000
```

**Terminal 3: ngrok**
```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok-free.app`).

## Configure WhatsApp Webhook

1. Go to [Meta Developer Console](https://developers.facebook.com)
2. Navigate to **WhatsApp** → **Configuration**
3. Edit webhook:
   - **Callback URL**: `https://abc123.ngrok-free.app/webhook`
   - **Verify Token**: (from your `.env`)
4. Subscribe to **messages** events

## Testing

Send a WhatsApp message to your bot. Check all three terminals for activity.

**ngrok web interface** (useful for debugging):
```bash
open http://127.0.0.1:4040
```

## Free vs Paid

**Free Tier:**
- ✅ HTTPS tunnels, web interface
- ❌ Random URL on each restart

**Personal ($8/month):**
- ✅ Static URL (never changes)
- ✅ No rate limits

Start with free tier. Upgrade if URL changes become annoying.

## Common Issues

**Webhook verification fails:**
- Check FastAPI is running on port 8000
- Verify ngrok tunnel is active
- Ensure verify token matches `.env`

**Bot doesn't reply:**
- Check `OPENROUTER_API_KEY` is valid
- Verify `WHATSAPP_ACCESS_TOKEN` is correct
- Check FastAPI logs for errors

**URL changes every restart:**
Workaround for free tier - update webhook URL in Meta console each time, or upgrade to paid plan for static URL.
