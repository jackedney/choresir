# Local Development Guide

## Local Webhook Testing with ngrok

### Prerequisites

1. **Install ngrok:**
   ```bash
   brew install ngrok
   ```

2. **Set up ngrok account:**
   - Sign up at https://ngrok.com
   - Get auth token from dashboard
   - Configure: `ngrok config add-authtoken <your-token>`

### Setup Process

1. **Start PocketBase locally:**
   ```bash
   ./pocketbase serve
   ```
   - Access admin UI at http://127.0.0.1:8090/_/
   - Create admin account if first run

2. **Start FastAPI application:**
   ```bash
   uv run fastapi dev src/main.py --port 8000
   ```

3. **Start ngrok tunnel:**
   ```bash
   ./scripts/start_ngrok.sh
   ```
   - Default port: 8000
   - Custom port: `./scripts/start_ngrok.sh 8080`

4. **Configure Meta Developer Console:**
   - Navigate to: https://developers.facebook.com/apps
   - Select your app → WhatsApp → Configuration
   - Click "Edit" on webhook settings
   - Set Callback URL: `https://<your-ngrok-url>/webhook`
   - Set Verify Token: (match `WHATSAPP_VERIFY_TOKEN` in `.env`)
   - Subscribe to message events
   - Click "Verify and Save"

### Environment Variables

Create `.env` file in project root:

```env
# PocketBase
POCKETBASE_URL=http://127.0.0.1:8090

# OpenRouter
OPENROUTER_API_KEY=sk-or-...

# WhatsApp
WHATSAPP_VERIFY_TOKEN=your_verify_token_here
WHATSAPP_APP_SECRET=your_app_secret_here
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here

# Logfire
LOGFIRE_TOKEN=your_logfire_token_here

# House Config
HOUSE_CODE=FAMSAC
HOUSE_PASSWORD=welcomehome

# Model (optional)
MODEL_ID=anthropic/claude-3.5-sonnet
```

### Testing Workflow

1. Send WhatsApp message to your test number
2. Check ngrok web interface at http://127.0.0.1:4040 to see incoming requests
3. View FastAPI logs for processing
4. Check Logfire dashboard for traces
5. Verify response in WhatsApp

### Common Issues

#### Webhook Verification Fails
- **Cause:** Verify token mismatch
- **Fix:** Ensure `WHATSAPP_VERIFY_TOKEN` in `.env` matches Meta console

#### Signature Validation Fails
- **Cause:** Incorrect `WHATSAPP_APP_SECRET`
- **Fix:** Copy exact secret from Meta console → App Settings → Basic

#### Messages Not Processed
- **Cause:** Background task error
- **Fix:** Check FastAPI logs for exceptions

#### ngrok URL Changes on Restart
- **Cause:** Free tier assigns random URLs
- **Fix:** Update webhook URL in Meta console, or upgrade to paid plan for static URLs

#### Rate Limiting
- **Cause:** Too many requests to WhatsApp API
- **Fix:** Check rate limit logic in `src/interface/whatsapp_sender.py`

### Debugging Tools

**ngrok Web Interface:**
- URL: http://127.0.0.1:4040
- Features: Request inspector, replay requests

**FastAPI Docs:**
- URL: http://127.0.0.1:8000/docs
- Features: Interactive API testing

**PocketBase Admin:**
- URL: http://127.0.0.1:8090/_/
- Features: View/edit database records

**Logfire Dashboard:**
- URL: https://logfire.pydantic.dev
- Features: Distributed tracing, performance monitoring

### Development Commands

```bash
# Install dependencies
uv sync

# Run linter
uv run ruff check src/

# Run formatter
uv run ruff format src/

# Run type checker
uv run ty src/

# Run tests
uv run pytest

# Start dev server with auto-reload
uv run fastapi dev src/main.py

# Start production server
uv run fastapi run src/main.py
```

### Hot Reload

FastAPI dev mode includes auto-reload. Changes to Python files will automatically restart the server.

**Note:** PocketBase does not auto-reload. Restart manually if schema changes.
