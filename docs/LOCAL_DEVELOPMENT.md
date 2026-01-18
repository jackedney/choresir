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

### Quick Start (Recommended)

#### 1. Set up ngrok static domain (one-time setup)

Free ngrok accounts include 1 static domain. To configure it:

```bash
task setup-ngrok
```

Follow the prompts to:
1. Visit the ngrok dashboard to create/view your static domain
2. Save the domain for reuse

**Note:** If you skip this step, ngrok will use a random URL that changes each restart.

#### 2. Start all services

Use the integrated dev command to start all services at once:

```bash
task dev
```

This will automatically:
- Install PocketBase if not present
- Start PocketBase on http://127.0.0.1:8090
- Create admin account (if needed)
- Start FastAPI on http://0.0.0.0:8000
- Start ngrok tunnel with your static domain (or random URL if not configured)
- Display the webhook URL

Press Ctrl+C to stop all services.

### Manual Setup (Alternative)

If you prefer to run services separately:

1. **Start PocketBase locally:**
   ```bash
   task install-pocketbase  # First time only
   ./pocketbase serve
   ```
   - Access admin UI at http://127.0.0.1:8090/_/
   - Create admin account: `./pocketbase superuser upsert admin@test.local testpassword123`

2. **Start FastAPI application:**
   ```bash
   uv run fastapi dev src/main.py --port 8000
   ```

3. **Start ngrok tunnel:**
   ```bash
   ngrok http 8000
   ```

### Webhook Configuration

4. **Configure Twilio Console:**
   - Go to: https://console.twilio.com
   - Navigate to Messaging → Try it Out → WhatsApp Sandbox
   - In "Sandbox Configuration" section
   - Set "When a message comes in" webhook URL: `https://<your-ngrok-url>/webhook`
   - Set HTTP method: POST
   - Click "Save"

### Environment Variables

Create `.env` file in project root:

```env
# PocketBase
POCKETBASE_URL=http://127.0.0.1:8090

# OpenRouter
OPENROUTER_API_KEY=sk-or-...

# Twilio
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Logfire
LOGFIRE_TOKEN=your_logfire_token_here

# House Config
HOUSE_CODE=FAMSAC
HOUSE_PASSWORD=welcomehome

# Model (optional)
MODEL_ID=anthropic/claude-3.5-sonnet

# Admin Notifications (optional)
ENABLE_ADMIN_NOTIFICATIONS=true
ADMIN_NOTIFICATION_COOLDOWN_MINUTES=60
```

### Admin Notification Configuration

The system sends WhatsApp notifications to admin users when critical errors occur (e.g., service quota exceeded, authentication failures).

**Configuration Options:**

- `ENABLE_ADMIN_NOTIFICATIONS` (default: `true`)
  - Controls whether admin notifications are sent
  - Set to `false` to disable all admin notifications during local testing
  - Useful when testing error scenarios to avoid spamming admin accounts

- `ADMIN_NOTIFICATION_COOLDOWN_MINUTES` (default: `60`)
  - Time period between notifications for the same error category
  - Prevents notification spam for recurring errors
  - Minimum recommended value: 5 minutes

**When Notifications Are Triggered:**

Admin notifications are sent for critical errors that require immediate attention:
- **Service Quota Exceeded**: API rate limits or quota exhaustion
- **Authentication Failed**: Credential or permission issues with external services

Transient errors (network timeouts, temporary service disruptions) do not trigger notifications.

**Disabling for Testing:**

To test error handling without sending notifications:

```bash
# In your .env file
ENABLE_ADMIN_NOTIFICATIONS=false
```

### Testing Workflow

1. Send WhatsApp message to your test number
2. Check ngrok web interface at http://127.0.0.1:4040 to see incoming requests
3. View FastAPI logs for processing
4. Check Logfire dashboard for traces
5. Verify response in WhatsApp

### Common Issues

#### Webhook Fails
- **Cause:** Webhook URL or configuration issue
- **Fix:** Ensure webhook URL is correct in Twilio console and HTTP method is POST

#### Authentication Fails
- **Cause:** Incorrect Twilio credentials
- **Fix:** Verify `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env` match Twilio console

#### Messages Not Processed
- **Cause:** Background task error
- **Fix:** Check FastAPI logs for exceptions

#### ngrok URL Changes on Restart
- **Cause:** Free tier assigns random URLs
- **Fix:** Update webhook URL in Twilio console, or upgrade to paid plan for static URLs

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
# Start all services (PocketBase, FastAPI, ngrok)
task dev

# Stop all services
task stop-dev

# Install PocketBase only
task install-pocketbase

# Install dependencies
uv sync

# Run linter
task lint

# Run formatter
task format

# Run tests
task test

# Run unit tests only
task test-unit

# Run integration tests
task test-integration

# Start dev server with auto-reload (manual)
uv run fastapi dev src/main.py

# Start production server (manual)
uv run fastapi run src/main.py
```

### Hot Reload

FastAPI dev mode includes auto-reload. Changes to Python files will automatically restart the server.

**Note:** PocketBase does not auto-reload. Restart manually if schema changes.
