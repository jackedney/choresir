# choresir Setup Guide

This guide outlines all human configuration required to get choresir running, from local development to production deployment.

---

## Prerequisites

- Python 3.12+
- `uv` package manager
- Git
- A Twilio account
- A WhatsApp phone number for your bot

---

## Part 1: Initial Setup (Local Development)

### Step 1: Clone and Install Dependencies

```bash
git clone https://github.com/jackedney/choresir.git
cd choresir
uv sync
```

### Step 2: Configure Environment Variables

Create a `.env` file in the project root:

```bash
# PocketBase Configuration
POCKETBASE_URL=http://127.0.0.1:8090

# Redis Configuration (REQUIRED for leaderboard caching)
REDIS_URL=redis://localhost:6379

# OpenRouter Configuration (REQUIRED)
OPENROUTER_API_KEY=<get from openrouter.ai>

# Twilio Configuration (REQUIRED for webhook)
TWILIO_ACCOUNT_SID=<get from Twilio Console>
TWILIO_AUTH_TOKEN=<get from Twilio Console>
TWILIO_WHATSAPP_NUMBER=<get from Twilio Console, format: whatsapp:+14155238886>

# Pydantic Logfire Configuration (OPTIONAL but recommended)
LOGFIRE_TOKEN=<get from logfire.pydantic.dev>

# House Onboarding Configuration
HOUSE_CODE=<create a memorable code, e.g., "FAMILY2024">
HOUSE_PASSWORD=<create a secure password>

# Admin Notification Configuration (OPTIONAL)
ENABLE_ADMIN_NOTIFICATIONS=true  # Set to false to disable admin notifications
ADMIN_NOTIFICATION_COOLDOWN_MINUTES=60  # Minimum time between notifications (default: 60)

# AI Model Configuration (OPTIONAL - has sensible default)
MODEL_ID=anthropic/claude-3.5-sonnet
```

### Step 3: Start Development Environment

The easiest way to start all services (PocketBase, FastAPI, ngrok) is:

```bash
task dev
```

This automatically:
- Downloads and installs PocketBase (if needed)
- Creates the admin account
- Starts all services
- Shows you the ngrok URL for webhook configuration

For more control, start services individually (see step-by-step instructions below).

---

## Part 2: External Service Setup

### A. Redis (Leaderboard Caching)

**Required for:** Leaderboard functionality

**IMPORTANT:** Redis is REQUIRED for the leaderboard feature. Without Redis configured, leaderboard endpoints (`/leaderboard`, `/stats`) will fail with connection errors. Redis is used to cache leaderboard data to improve performance and reduce database load.

#### Option 1: Local Development with Docker (Recommended)

```bash
# Start Redis using Docker
docker run -d -p 6379:6379 --name choresir-redis redis:alpine

# Verify it's running
docker ps | grep redis
```

Add to `.env`:
```bash
REDIS_URL=redis://localhost:6379
```

#### Option 2: Local Development with Homebrew (macOS)

```bash
# Install Redis
brew install redis

# Start Redis
brew services start redis

# Verify it's running
redis-cli ping  # Should return "PONG"
```

Add to `.env`:
```bash
REDIS_URL=redis://localhost:6379
```

#### Option 3: Redis Cloud (Free Tier)

For development or production, you can use a managed Redis instance:

1. Go to https://redis.com/try-free/
2. Create a free account
3. Create a new database
4. Note your connection details:
   - **Endpoint:** `redis-12345.c1.us-east-1-2.ec2.redns.redis-cloud.com:12345`
   - **Password:** Copy from dashboard

Add to `.env`:
```bash
REDIS_URL=redis://:your-password@redis-12345.c1.us-east-1-2.ec2.redns.redis-cloud.com:12345
```

**Cost:** Free tier includes 30MB storage (more than enough for leaderboard data)

#### Testing Redis Connection

```bash
# Using redis-cli (if installed locally)
redis-cli -u redis://localhost:6379 ping

# Or test from Python
uv run python -c "import redis; r = redis.from_url('redis://localhost:6379'); print(r.ping())"
```

### B. OpenRouter (AI Model Access)

**Required for:** Agent execution

1. Go to https://openrouter.ai
2. Create an account
3. Navigate to API Keys section
4. Generate a new API key
5. Add credits to your account (minimum $5 recommended)
6. Copy API key to `.env` as `OPENROUTER_API_KEY`

**Cost Estimate:** ~$0.10/day for moderate household usage

### C. Twilio WhatsApp API

**Required for:** Receiving and sending messages

#### Step 1: Create Twilio Account
1. Go to https://www.twilio.com
2. Sign up for an account
3. Navigate to Console → Messaging → Try it Out → WhatsApp Sandbox

#### Step 2: Connect Your Phone
1. Send the join code shown in the sandbox to the Twilio number
2. Wait for confirmation message

#### Step 3: Get Credentials
1. Go to Console → Account → API keys & tokens
2. Copy Account SID → `TWILIO_ACCOUNT_SID`
3. Copy Auth Token → `TWILIO_AUTH_TOKEN`
4. Note sandbox number → `TWILIO_WHATSAPP_NUMBER` (format: `whatsapp:+14155238886`)

#### Step 4: Configure Webhook (After setup is complete)

See [Part 4: Webhook Setup](#part-4-webhook-setup-local-testing) below.

### D. Pydantic Logfire (Observability)

**Optional but recommended for:** Monitoring, debugging, performance tracking

1. Go to https://logfire.pydantic.dev
2. Create an account
3. Create a new project
4. Copy the project token
5. Add to `.env` as `LOGFIRE_TOKEN`

**Cost:** Free tier available (generous limits for development)

---

## Part 3: WhatsApp Template Messages

**Required for:** Sending messages outside the 24-hour window

### Templates to Register

You need to create and get approval for these templates in Twilio Content Editor:

#### 1. Chore Reminder Template

**Name:** `chore_reminder`

**Category:** Utility

**Template:**
```
Hello {{1}}, this is a reminder about your chore: {{2}}.
Deadline: {{3}}.
```

**Variables:**
1. User name
2. Chore title
3. Deadline date

#### 2. Verification Request Template

**Name:** `verification_request`

**Category:** Utility

**Template:**
```
{{1}} has completed: {{2}}.
Please verify or reject this completion.
```

**Variables:**
1. User name
2. Chore title

#### 3. Conflict Notification Template

**Name:** `conflict_notification`

**Category:** Utility

**Template:**
```
A chore completion is in conflict: {{1}}.
Your vote is needed to resolve this.
```

**Variables:**
1. Chore title

### How to Submit Templates

1. Go to Twilio Console → Messaging → Content Editor
2. Click "Create new Content"
3. Select "WhatsApp" as the channel
4. Fill in the template details
5. Submit for approval
6. Wait 24-48 hours for Twilio approval

**Note:** Templates can only be edited by resubmitting. Changes require re-approval.

---

## Part 4: Obtaining Template Content SIDs

**Required for:** Sending template messages in your code

After WhatsApp approves your templates (typically 24-48 hours after submission), you need to retrieve the Content SIDs to use them in your application.

### Where to Find Content SIDs

#### Method 1: Twilio Console (Easiest)

1. Go to Twilio Console → **Messaging** → **Content Editor**
2. Find your approved template in the list (status should show "Approved")
3. Click on the template name to open details
4. Copy the **Content SID** (format: `HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

#### Method 2: Twilio API

```bash
curl -X GET "https://content.twilio.com/v1/Content" \
  -u "TWILIO_ACCOUNT_SID:TWILIO_AUTH_TOKEN"
```

Look for your template name in the response and copy the `sid` field.

### Template SID Mapping

You'll need Content SIDs for these templates:

| Template Name | Purpose | Required For |
|---------------|---------|--------------|
| `chore_reminder` | Send scheduled chore deadline reminders | Chore scheduler system |
| `verification_request` | Request chore completion verification with approve/reject buttons | Verification workflow |
| `household_update` | Notify members of household changes (new members, removals, settings) | Admin operations |
| `conflict_notification` | Alert members when verification is disputed | Conflict resolution |

### Adding Content SIDs to Your Code

Once you have all Content SIDs, update your configuration file:

```python
# src/interface/whatsapp_templates.py
TEMPLATE_CONTENT_SIDS = {
    "chore_reminder": "HXabcdef1234567890abcdef1234567890",
    "verification_request": "HXfedcba0987654321fedcba0987654321",
    "household_update": "HX1122334455667788991122334455667788",
    "conflict_notification": "HX9988776655443322119988776655443322",
}
```

**Important:** Replace the example SIDs with your actual Content SIDs from Twilio Console.

### Testing Your Templates

After adding Content SIDs to your code, test each template:

#### Quick Test via Twilio Console

1. Go to **Messaging** → **Content Editor**
2. Click on your template
3. Click **"Send Test Message"**
4. Fill in:
   - **To:** Your WhatsApp number
   - **From:** Your Twilio WhatsApp sender
   - **Variables:** Example values for `{{1}}`, `{{2}}`, etc.
5. Check WhatsApp to verify the message appears correctly

#### Test via Code

```python
from twilio.rest import Client

client = Client(account_sid, auth_token)

message = client.messages.create(
    from_='whatsapp:+14155238886',
    content_sid='HXabcdef1234567890abcdef1234567890',  # Your Content SID
    content_variables={
        "1": "Alice",
        "2": "Wash Dishes", 
        "3": "Jan 16, 8:00 PM"
    },
    to='whatsapp:+1234567890'
)
```

**Note:** Template approval typically takes 24-48 hours. You can test basic functionality without templates, but scheduled reminders and verification buttons require approved templates.

---

## Part 5: Webhook Setup (Local Testing)

**Prerequisites:** Development environment must be running.

### Step 1: Install ngrok

```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

### Step 2: Create ngrok Account

1. Go to https://ngrok.com
2. Sign up for free account
3. Get your auth token from dashboard
4. Configure: `ngrok config add-authtoken <your-token>`

### Step 3: Start ngrok Tunnel

```bash
# Start your FastAPI app first
uv run fastapi run src/main.py --port 8000

# In another terminal, start ngrok
ngrok http 8000
```

ngrok will output a URL like: `https://abc123.ngrok-free.app`

### Step 4: Configure Twilio Webhook

1. Go to Twilio Console → Messaging → Try it Out → WhatsApp Sandbox
2. In the "Sandbox Configuration" section
3. Set "When a message comes in" webhook URL: `https://abc123.ngrok-free.app/webhook`
4. Set HTTP method to: POST
5. Click "Save"

### Step 5: Test the Webhook

1. Send a WhatsApp message to your Twilio sandbox number
2. Check the FastAPI logs for incoming webhook
3. Check Logfire for detailed traces (if configured)

**Note:** ngrok free tier URLs change on restart. You'll need to update the webhook URL in Twilio console each time ngrok restarts.

---

## Part 6: First User Setup

After the system is running, you need to create the first admin user.

### Option 1: Via WhatsApp (Recommended)

1. Send a message to the bot: `/house join MyHouse` (replace MyHouse with your configured HOUSE_NAME)
2. Follow the bot's prompts to provide your password and name
3. The bot will create your account with status "pending"
4. Go to PocketBase Admin UI: http://127.0.0.1:8090/_/
5. Navigate to Collections → users
6. Find your user record
7. Edit: Change `role` from "member" to "admin"
8. Edit: Change `status` from "pending" to "active"
9. Save

### Option 2: Manually in PocketBase

1. Go to PocketBase Admin UI: http://127.0.0.1:8090/_/
2. Navigate to Collections → users
3. Click "New Record"
4. Fill in:
   - `phone`: Your phone number in E.164 format (e.g., "+1234567890")
   - `name`: Your name
   - `role`: "admin"
   - `status`: "active"
5. Save

Now you can approve other members via WhatsApp!

---

## Part 7: Running the Application

### Local Development

```bash
# Terminal 1: Start PocketBase
./pocketbase serve

# Terminal 2: Start FastAPI app
uv run fastapi run src/main.py --port 8000

# Terminal 3: Start ngrok (for WhatsApp webhook)
ngrok http 8000
```

### Verification Checklist

- [ ] PocketBase running at http://127.0.0.1:8090
- [ ] Redis running at localhost:6379 (test with `redis-cli ping`)
- [ ] FastAPI running at http://localhost:8000
- [ ] ngrok tunnel active (if testing WhatsApp)
- [ ] Webhook configured in Twilio Console
- [ ] At least one admin user exists
- [ ] `.env` file has all required keys
- [ ] OpenRouter API key has credits

---

## Part 8: Production Deployment (Railway)

**Prerequisites:** Tasks 28-29 must be completed.

### Step 1: Create Railway Project

1. Go to https://railway.app
2. Create a new project
3. Connect your GitHub repository

### Step 2: Deploy PocketBase Service

1. Add a new service in Railway
2. Select "Empty Service"
3. Configure:
   - **Name:** pocketbase
   - **Build Command:** (none - uses pre-built binary)
   - **Start Command:** `./pocketbase serve --http=0.0.0.0:$PORT`
4. Add a **volume** mounted to `/pb_data` (for persistent storage)
5. Set environment variables: (none needed for PocketBase)
6. Deploy

### Step 3: Deploy FastAPI Service

1. Add a new service in Railway
2. Connect to your GitHub repository
3. Configure:
   - **Name:** choresir-api
   - **Build Command:** `uv sync`
   - **Start Command:** `uv run fastapi run src/main.py --port $PORT`
4. Set environment variables (ALL from your `.env`):
   - `POCKETBASE_URL=<internal Railway URL of PocketBase service>`
   - `OPENROUTER_API_KEY=<your key>`
   - `TWILIO_ACCOUNT_SID=<from Twilio>`
   - `TWILIO_AUTH_TOKEN=<from Twilio>`
   - `TWILIO_WHATSAPP_NUMBER=<from Twilio>`
   - `LOGFIRE_TOKEN=<your token>`
   - `HOUSE_CODE=<your code>`
   - `HOUSE_PASSWORD=<your password>`
   - `MODEL_ID=anthropic/claude-3.5-sonnet`
5. Deploy

### Step 4: Update WhatsApp Webhook

1. Get the public URL from Railway (e.g., `https://choresir-api.railway.app`)
2. Go to Twilio Console → Messaging → WhatsApp Sandbox → Sandbox Configuration
3. Update webhook URL to: `https://choresir-api.railway.app/webhook`
4. Set HTTP method to POST and save

### Step 5: Production Verification

- [ ] PocketBase service healthy
- [ ] FastAPI service healthy
- [ ] Webhook configured in Twilio
- [ ] Test message from WhatsApp works
- [ ] Logfire shows traces (if configured)
- [ ] PocketBase data persists across deploys

---

## Troubleshooting

### Common Issues

#### "Invalid credentials" when joining
- Check `HOUSE_CODE` and `HOUSE_PASSWORD` in `.env`
- Ensure they match what the user is sending

#### Webhook fails
- Check webhook URL is correct and accessible in Twilio console
- Ensure HTTP method is set to POST
- Check FastAPI logs for webhook attempts

#### Agent not responding
- Check `OPENROUTER_API_KEY` is valid and has credits
- Check Logfire for error traces
- Verify PocketBase is running and accessible

#### Messages not sending
- Check `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are valid
- Verify `TWILIO_WHATSAPP_NUMBER` is correct (format: `whatsapp:+14155238886`)
- Ensure you're within the 24-hour window OR using template messages

#### Database schema errors
- Delete `pb_data/` directory and restart PocketBase
- Schema will auto-sync from code on FastAPI startup

### Getting Help

- Check Logfire dashboard for detailed error traces
- Review FastAPI logs: `uv run fastapi run src/main.py --log-level debug`
- Check PocketBase logs in the admin UI
- Review Twilio Console webhook logs

---

## Cost Breakdown

### Development (Free/Minimal)
- PocketBase: Free (self-hosted)
- Redis: Free (self-hosted via Docker or Homebrew)
- ngrok: Free tier (URL changes on restart)
- Logfire: Free tier (5GB/month)
- OpenRouter: ~$0.10/day (~$3/month)
- **Total:** ~$3/month

### Production (Railway)
- Railway: ~$5-10/month (PocketBase + FastAPI)
- Redis Cloud: Free tier (30MB) or ~$5/month for more capacity
- OpenRouter: ~$0.10/day (~$3/month)
- Logfire: Free tier or ~$20/month for pro
- Twilio WhatsApp API: Free sandbox, $0.005/message for production
- **Total:** ~$8-38/month

---

## Security Checklist

- [ ] Never commit `.env` file to git
- [ ] Use strong `HOUSE_PASSWORD`
- [ ] Rotate `TWILIO_AUTH_TOKEN` periodically
- [ ] Enable 2FA on Twilio account
- [ ] Restrict Railway service access
- [ ] Monitor OpenRouter usage for anomalies
- [ ] Regularly backup PocketBase data (volume snapshots)
- [ ] Use HTTPS for all production endpoints

---

## Next Steps

Once setup is complete:

1. Invite household members (share house code + password)
2. Admin approves members via WhatsApp
3. Define recurring chores
4. Start logging completions
5. Monitor via Logfire dashboard
6. Review analytics/leaderboards weekly

---

**Last Updated:** 2026-01-15
**Version:** 1.0
**Status:** Ready for use after Task 23 completion
