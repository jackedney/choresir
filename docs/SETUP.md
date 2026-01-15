# choresir Setup Guide

This guide outlines all human configuration required to get choresir running, from local development to production deployment.

---

## Prerequisites

- Python 3.12+
- `uv` package manager
- Git
- A Meta/Facebook Developer account
- A WhatsApp phone number for your bot

---

## Part 1: Initial Setup (Local Development)

### Step 1: Clone and Install Dependencies

```bash
git clone <repository-url>
cd wellington
uv sync
```

### Step 2: Download PocketBase

Download the PocketBase binary for your platform from https://pocketbase.io/docs/

```bash
# macOS/Linux
wget https://github.com/pocketbase/pocketbase/releases/download/v0.XX.X/pocketbase_X.X.X_darwin_amd64.zip
unzip pocketbase_*.zip
chmod +x pocketbase

# The binary should be in the project root
./pocketbase serve
```

### Step 3: Create PocketBase Admin Account

1. Start PocketBase: `./pocketbase serve`
2. Navigate to http://127.0.0.1:8090/_/
3. Create an admin account (save credentials securely)
4. Database schema will auto-sync when you start the FastAPI app

### Step 4: Configure Environment Variables

Create a `.env` file in the project root:

```bash
# PocketBase Configuration
POCKETBASE_URL=http://127.0.0.1:8090

# OpenRouter Configuration (REQUIRED)
OPENROUTER_API_KEY=<get from openrouter.ai>

# WhatsApp Configuration (REQUIRED for webhook)
WHATSAPP_VERIFY_TOKEN=<create a secure random token>
WHATSAPP_APP_SECRET=<get from Meta Developer Console>
WHATSAPP_ACCESS_TOKEN=<get from Meta Developer Console>
WHATSAPP_PHONE_NUMBER_ID=<get from Meta Developer Console>

# Pydantic Logfire Configuration (OPTIONAL but recommended)
LOGFIRE_TOKEN=<get from logfire.pydantic.dev>

# House Onboarding Configuration
HOUSE_CODE=<create a memorable code, e.g., "FAMILY2024">
HOUSE_PASSWORD=<create a secure password>

# AI Model Configuration (OPTIONAL - has sensible default)
MODEL_ID=anthropic/claude-3.5-sonnet
```

---

## Part 2: External Service Setup

### A. OpenRouter (AI Model Access)

**Required for:** Agent execution

1. Go to https://openrouter.ai
2. Create an account
3. Navigate to API Keys section
4. Generate a new API key
5. Add credits to your account (minimum $5 recommended)
6. Copy API key to `.env` as `OPENROUTER_API_KEY`

**Cost Estimate:** ~$0.10/day for moderate household usage

### B. WhatsApp Business API

**Required for:** Receiving and sending messages

#### Step 1: Create Meta Business Account

1. Go to https://business.facebook.com
2. Create a Business account
3. Complete business verification (may require business documents)

#### Step 2: Create WhatsApp Business App

1. Go to https://developers.facebook.com
2. Click "My Apps" → "Create App"
3. Select "Business" as the app type
4. Fill in app details
5. Add "WhatsApp" product to your app

#### Step 3: Configure WhatsApp

1. In the WhatsApp product section:
   - Select a phone number (test number provided by Meta or your own)
   - Note the **Phone Number ID** → add to `.env` as `WHATSAPP_PHONE_NUMBER_ID`
   - Generate a **Permanent Access Token** → add to `.env` as `WHATSAPP_ACCESS_TOKEN`

2. In App Settings → Basic:
   - Note the **App Secret** → add to `.env` as `WHATSAPP_APP_SECRET`

3. Create a **Verify Token** (any secure random string):
   - Generate: `openssl rand -hex 32`
   - Add to `.env` as `WHATSAPP_VERIFY_TOKEN`

#### Step 4: Configure Webhook (After Task 23 is complete)

See [Part 4: Webhook Setup](#part-4-webhook-setup-local-testing) below.

### C. Pydantic Logfire (Observability)

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

You need to create and get approval for these templates in Meta Developer Console:

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

1. Go to Meta Developer Console → Your App → WhatsApp → Message Templates
2. Click "Create Template"
3. Fill in the template details
4. Submit for approval
5. Wait 24-48 hours for Meta approval

**Note:** Templates can only be edited by resubmitting. Changes require re-approval.

---

## Part 4: Webhook Setup (Local Testing)

**Prerequisites:** Tasks 8-11 and Task 23 must be completed.

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

### Step 4: Configure WhatsApp Webhook

1. Go to Meta Developer Console → Your App → WhatsApp → Configuration
2. Click "Edit" next to Webhook
3. Enter the callback URL: `https://abc123.ngrok-free.app/webhook`
4. Enter your `WHATSAPP_VERIFY_TOKEN` (from `.env`)
5. Click "Verify and Save"
6. Subscribe to webhook fields:
   - ✅ messages
   - ✅ message_status (optional)

### Step 5: Test the Webhook

1. Send a WhatsApp message to your bot number
2. Check the FastAPI logs for incoming webhook
3. Check Logfire for detailed traces (if configured)

**Note:** ngrok free tier URLs change on restart. You'll need to update the webhook URL in Meta console each time ngrok restarts.

---

## Part 5: First User Setup

After the system is running, you need to create the first admin user.

### Option 1: Via WhatsApp (Recommended)

1. Send a message to the bot: "I want to join. Code: FAMILY2024, Password: your-password, Name: Your Name"
2. The bot will create your account with status "pending"
3. Go to PocketBase Admin UI: http://127.0.0.1:8090/_/
4. Navigate to Collections → users
5. Find your user record
6. Edit: Change `role` from "member" to "admin"
7. Edit: Change `status` from "pending" to "active"
8. Save

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

## Part 6: Running the Application

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
- [ ] FastAPI running at http://localhost:8000
- [ ] ngrok tunnel active (if testing WhatsApp)
- [ ] Webhook configured in Meta Developer Console
- [ ] At least one admin user exists
- [ ] `.env` file has all required keys
- [ ] OpenRouter API key has credits

---

## Part 7: Production Deployment (Railway)

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
   - `WHATSAPP_VERIFY_TOKEN=<your token>`
   - `WHATSAPP_APP_SECRET=<from Meta>`
   - `WHATSAPP_ACCESS_TOKEN=<from Meta>`
   - `WHATSAPP_PHONE_NUMBER_ID=<from Meta>`
   - `LOGFIRE_TOKEN=<your token>`
   - `HOUSE_CODE=<your code>`
   - `HOUSE_PASSWORD=<your password>`
   - `MODEL_ID=anthropic/claude-3.5-sonnet`
5. Deploy

### Step 4: Update WhatsApp Webhook

1. Get the public URL from Railway (e.g., `https://choresir-api.railway.app`)
2. Go to Meta Developer Console → WhatsApp → Configuration
3. Update webhook URL to: `https://choresir-api.railway.app/webhook`
4. Verify and save

### Step 5: Production Verification

- [ ] PocketBase service healthy
- [ ] FastAPI service healthy
- [ ] Webhook verified by Meta
- [ ] Test message from WhatsApp works
- [ ] Logfire shows traces (if configured)
- [ ] PocketBase data persists across deploys

---

## Troubleshooting

### Common Issues

#### "Invalid credentials" when joining
- Check `HOUSE_CODE` and `HOUSE_PASSWORD` in `.env`
- Ensure they match what the user is sending

#### Webhook fails verification
- Check `WHATSAPP_VERIFY_TOKEN` matches in both `.env` and Meta console
- Ensure webhook URL is correct and accessible
- Check FastAPI logs for verification attempts

#### Agent not responding
- Check `OPENROUTER_API_KEY` is valid and has credits
- Check Logfire for error traces
- Verify PocketBase is running and accessible

#### Messages not sending
- Check `WHATSAPP_ACCESS_TOKEN` is valid
- Verify `WHATSAPP_PHONE_NUMBER_ID` is correct
- Ensure you're within the 24-hour window OR using template messages

#### Database schema errors
- Delete `pb_data/` directory and restart PocketBase
- Schema will auto-sync from code on FastAPI startup

### Getting Help

- Check Logfire dashboard for detailed error traces
- Review FastAPI logs: `uv run fastapi run src/main.py --log-level debug`
- Check PocketBase logs in the admin UI
- Review Meta Developer Console webhook logs

---

## Cost Breakdown

### Development (Free/Minimal)
- PocketBase: Free (self-hosted)
- ngrok: Free tier (URL changes on restart)
- Logfire: Free tier (5GB/month)
- OpenRouter: ~$0.10/day (~$3/month)
- **Total:** ~$3/month

### Production (Railway)
- Railway: ~$5-10/month (PocketBase + FastAPI)
- OpenRouter: ~$0.10/day (~$3/month)
- Logfire: Free tier or ~$20/month for pro
- WhatsApp Business API: Free for low volume
- **Total:** ~$8-33/month

---

## Security Checklist

- [ ] Never commit `.env` file to git
- [ ] Use strong `HOUSE_PASSWORD`
- [ ] Rotate `WHATSAPP_VERIFY_TOKEN` periodically
- [ ] Enable 2FA on Meta Business account
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
