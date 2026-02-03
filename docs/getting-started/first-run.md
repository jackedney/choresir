# First Run

This guide covers running WhatsApp Home Boss for the first time, connecting WhatsApp, and verifying the setup.

## Prerequisites

Before starting, ensure you have completed:

- [Installation](./installation.md) - All dependencies installed
- [Configuration](./configuration.md) - Environment variables configured
- PocketBase running on <http://127.0.0.1:8090>
- Redis running on localhost:6379
- WAHA running on <http://127.0.0.1:3000>
- WAHA QR code scanned and WhatsApp connected

## Step 1: Start the Application

### Quick Start (Single Terminal)

Use the included task to start all services:

```bash
task dev
```

This command:

1. Starts PocketBase in the background
2. Waits for PocketBase to be ready
3. Creates/verifies admin account
4. Starts FastAPI server in the background
5. Waits for FastAPI to be ready
6. Starts ngrok (for webhooks)
7. Displays webhook URL for WAHA configuration

### Manual Start (Multiple Terminals)

For more control, start services manually in separate terminals:

#### Terminal 1: PocketBase

```bash
./pocketbase serve
```

PocketBase will start on <http://127.0.0.1:8090>

#### PocketBase expected output

```text
The server is starting...
> Server started at http://127.0.0.1:8090
```

#### Terminal 2: FastAPI

```bash
uv run fastapi dev src/main.py --port 8000
```

FastAPI will start on <http://0.0.0.0:8000>

#### FastAPI expected output

```text
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
startup_validation_complete extra={'status': 'ok'}
INFO:     Application startup complete.
```

### Error: Startup validation failed: HOUSE_CODE credential not configured

**Solution:** Verify `.env` file exists with `HOUSE_CODE` and `HOUSE_PASSWORD`
set.

#### Terminal 3: ngrok (Optional for External Webhook)

If using WAHA's webhook functionality (for production or remote testing), start ngrok:

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`) for webhook configuration.

### Verify Services Are Running

Check that all services are healthy:

```bash
# PocketBase
curl http://127.0.0.1:8090/api/health
# Expected: {"status":"ok"}

# FastAPI
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

Both should return healthy status.

## Step 2: Connect WAHA to WhatsApp

If you haven't already connected WAHA to WhatsApp:

1. Open <http://127.0.0.1:3000> in your browser
2. You should see your connected WhatsApp account (from configuration step)
3. Verify you see recent messages in the WAHA dashboard

### If not connected

1. Click "Connect" or "Scan QR Code" in WAHA
2. Open WhatsApp on your phone
3. Tap Menu → Linked Devices → Link a Device
4. Scan the QR code displayed in WAHA dashboard

## Step 3: Create First Admin User

### Option 1: Via WhatsApp (Recommended)

Send a message to your WhatsApp number (the one connected to WAHA):

```text
Join HOUSE123 SecretPass YourName
```

Replace:

- `HOUSE123` with your `HOUSE_CODE` from `.env`
- `SecretPass` with your `HOUSE_PASSWORD` from `.env`
- `YourName` with your display name

#### User creation bot response

```text
Welcome to MyHouse! I've created your account. An admin will need to approve
you before you can access household features.
```

### Option 2: Manually in PocketBase

1. Open <http://127.0.0.1:8090/_/> in your browser
2. Log in with admin credentials from `.env`
3. Navigate to Collections → users
4. Click "New Record"
5. Fill in:

   - `phone`: Your phone number in E.164 format (e.g., `+1234567890`)
   - `name`: Your name
   - `role`: `admin`
   - `status`: `active`

6. Save

### Approve Admin User (if using Option 1)

If you created the user via WhatsApp, approve them in PocketBase:

1. Open <http://127.0.0.1:8090/_/> in your browser
2. Navigate to Collections → users
3. Find your user record (search by phone number)
4. Click "Edit"
5. Change `role` to `admin`
6. Change `status` to `active`
7. Save

## Step 4: Send First Message

Now test that the bot responds correctly.

### Test Basic Message

Send a message to your WhatsApp:

```text
Hello
```

#### Expected bot response

```text
Hello! I'm choresir, your household operating system.

You can ask me to:
• Create or manage chores
• Log chore completions
• View your household leaderboard
• And more!

What would you like to do?
```

### No bot response

1. Check FastAPI logs for errors: `tail -f fastapi.log`
2. Check WAHA dashboard for incoming/outgoing messages
3. Verify user status is `active` in PocketBase
4. Check OpenRouter API key has credits
5. Verify webhook is configured (if using ngrok)

### Test Chore Creation

Send a natural language command:

```text
Remind Alice to water the plants every Tuesday
```

#### Chore creation bot response

```text
I've created a chore:
• Title: Water plants
• Assigned to: Alice
• Schedule: Every Tuesday

Alice will receive reminders before the deadline. When she completes it, household
members will verify.
```

### Test Chore Completion

Log a completion:

```text
I watered the plants
```

#### Chore completion bot response

```text
Thanks for logging your completion! Household members will verify your work.

[Awaiting verification...]
```

#### Expected FastAPI log entries

```text
INFO:     startup_validation_complete extra={'status': 'ok'}
INFO:     127.0.0.1:xxxxx - "POST /webhook HTTP/1.1" 200 OK
startup_validation complete
User action extra={'user_id': '...', 'action': 'message_received'}
```

### Check WAHA Dashboard

Open <http://127.0.0.1:3000> and verify:

- Incoming messages appear in the dashboard
- Bot responses are sent successfully
- No error messages in WAHA logs

### Check PocketBase Data

1. Open <http://127.0.0.1:8090/_/> in your browser
2. Navigate to Collections → users
3. Verify your user record exists with `status: active`
4. Navigate to Collections → chores
5. Verify chore records were created from your messages
6. Navigate to Collections → logs
7. Verify chore completion logs were created

## Verification Checklist

Complete these checks to verify everything is working:

- [ ] PocketBase running on <http://127.0.0.1:8090>
- [ ] Redis running on localhost:6379
- [ ] WAHA running on <http://127.0.0.1:3000>
- [ ] FastAPI running on <http://localhost:8000>
- [ ] FastAPI health check passes: `curl http://localhost:8000/health`
- [ ] WAHA connected to WhatsApp (QR code scanned)
- [ ] Admin user exists in PocketBase with `role: admin` and `status: active`
- [ ] Bot responds to "Hello" message
- [ ] Bot can create chores from natural language
- [ ] Bot can log chore completions
- [ ] Chores and logs appear in PocketBase
- [ ] No errors in FastAPI logs
- [ ] No errors in WAHA dashboard

## Stopping Services

### Stop All Services

Use the task to stop everything:

```bash
task down
```

This stops PocketBase, FastAPI, and ngrok, and cleans up log files.

### Manual Stop

```bash
# Terminal 1: Stop PocketBase (Ctrl+C)
# Terminal 2: Stop FastAPI (Ctrl+C)
# Terminal 3: Stop ngrok (Ctrl+C)
```

### Stop Docker Services

To stop Redis and WAHA:

```bash
docker-compose down
```

To stop and remove all data (clean slate):

```bash
docker-compose down -v
```

**Warning:** `-v` removes all Redis and WAHA data.

## Common Issues

### Bot doesn't respond to messages

**Symptoms:** Messages sent to WhatsApp receive no reply.

**Possible causes:**

1. User not approved (`status: pending` in PocketBase)
2. User banned (`status: banned` in PocketBase)
3. OpenRouter API key invalid or out of credits
4. WAHA not connected to WhatsApp
5. Webhook not receiving messages

**Solutions:**

1. Check user status in PocketBase Admin UI
2. Verify OpenRouter API key has credits: <https://openrouter.ai/credits>
3. Verify WAHA dashboard shows your WhatsApp account
4. Check FastAPI logs for webhook reception errors
5. Test webhook manually:

   ```bash
   curl -X POST http://localhost:8000/webhook \
     -H "Content-Type: application/json" \
     -d '{"session":"test","message":{"from":"1234567890","text":"hello"}}'
   ```

### Chores not being created

**Symptoms:** Bot responds but doesn't create chores.

**Possible causes:**

1. Agent not understanding the request
2. PocketBase write error
3. Missing required fields in chore creation

**Solutions:**

1. Try more explicit language: "Create a chore for Alice to water plants every Tuesday"
2. Check FastAPI logs for agent errors
3. Check PocketBase Admin UI → chores collection for records
4. Check Logfire for agent traces (if configured)

### Verification buttons not working

**Symptoms:** Bot sends verification requests but buttons don't respond.

**Possible causes:**

1. WAHA button handling not configured
2. Webhook not parsing button payloads correctly

**Solutions:**

1. Check WAHA dashboard for button configuration
2. Verify webhook receives button clicks in logs
3. Test button payload manually in PocketBase

### Scheduled reminders not sending

**Symptoms:** Reminders aren't being sent at scheduled times.

**Possible causes:**

1. Scheduler not running
2. Cron expression invalid
3. WAHA not sending scheduled messages

**Solutions:**

1. Check scheduler health: `curl http://localhost:8000/health/scheduler`
2. Review scheduler logs in FastAPI logs
3. Check WAHA logs for send errors

### Memory issues or high resource usage

**Symptoms:** Application slows down or crashes over time.

**Possible causes:**

1. Cache growing unbounded
2. Background jobs accumulating
3. Database not cleaned up

**Solutions:**

1. Check Redis memory: `docker stats choresir-redis`
2. Review scheduler dead letter queue: `curl http://localhost:8000/health/scheduler`
3. Clean up old logs in PocketBase
4. Restart services: `task down && task dev`

## Next Steps

Congratulations! Your WhatsApp Home Boss is now running. Explore these next steps:

- [User Guide](../user-guide/index.md) - Learn about all available features and commands
- [Architecture Documentation](../architecture/index.md) - Understand how the system works
- [Contributors Guide](../contributors/index.md) - Learn how to extend and customize

### Invite Household Members

Share the join instructions with your household:

1. Share your `HOUSE_CODE` (e.g., "HOUSE123")
2. Share your `HOUSE_PASSWORD` through a secure channel
3. Tell them to message the bot: `Join HOUSE123 <password> <TheirName>`
4. Approve new members via WhatsApp or PocketBase Admin UI

### Create Recurring Chores

Start building your household chore system:

```text
Remind me to take out the trash every Friday evening
Remind Alice to pay bills on the 1st of every month
Remind Bob to walk the dog every morning at 7am
```

The bot will handle scheduling and reminders automatically.
