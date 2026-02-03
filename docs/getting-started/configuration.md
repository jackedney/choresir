# Configuration

This guide covers configuring WhatsApp Home Boss for local development.

## Environment Variables

All configuration is managed through environment variables, typically stored in a `.env`
file in the project root.

## Step 1: Create Environment File

Copy the example environment file to create your own:

```bash
cp .env.example .env
```

Never commit the `.env` file to version control as it contains sensitive credentials.

## Step 2: Configure Required Variables

Edit `.env` with your preferred editor and set the required variables:

```bash
nano .env  # or use your preferred editor
```

### Required Variables

#### PocketBase Configuration

```bash
# PocketBase server URL (default is fine for local development)
POCKETBASE_URL=http://127.0.0.1:8090

# PocketBase admin credentials (required for schema synchronization)
# These credentials are used by the application to create collections on startup
POCKETBASE_ADMIN_EMAIL=admin@example.com
POCKETBASE_ADMIN_PASSWORD=your_secure_admin_password
```

**Important:** These admin credentials are used by the application, not for user login. Choose a
strong password.

#### OpenRouter API Key

OpenRouter provides access to LLM models (Claude, GPT-4, etc.) for the agent system.

```bash
# Required for AI agent functionality
# Get your key from <https://openrouter.ai/keys>
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**How to get an API key:**

1. Visit <https://openrouter.ai>
2. Create an account or log in
3. Navigate to API Keys section
4. Click "Create new key"
5. Add credits (minimum $5 recommended for testing)

**Estimated cost:** ~$0.10/day for moderate household usage

#### WAHA Configuration

WAHA (WhatsApp HTTP API) provides the WhatsApp integration. It runs in Docker and
requires minimal configuration:

```bash
# WAHA base URL (default is fine for local development)
WAHA_BASE_URL=http://127.0.0.1:3000

# WAHA API key (optional - set if using WAHA Plus or for additional security)
WAHA_API_KEY=your_waha_api_key
```

For local development, the default `WAHA_BASE_URL` works without an API key.
Production deployments should set `WAHA_API_KEY`.

#### House Onboarding Configuration

These credentials control how users join your household:

```bash
# House name (shown in welcome messages)
HOUSE_NAME=MyHouse

# Secret code users send to join (e.g., "Join HOUSE123")
HOUSE_CODE=HOUSE123

# Password users provide after sending the code
HOUSE_PASSWORD=your_secret_house_password
```

**Security note:** Share the `HOUSE_CODE` with household members, but keep
`HOUSE_PASSWORD` private and share it through a secure channel (e.g., in person,
encrypted message).

### Optional Variables

#### Redis Configuration

```bash
# Redis connection URL for caching (default is fine for local Docker setup)
REDIS_URL=redis://localhost:6379
```

Redis is required for leaderboard caching. The default URL works with the Redis container
started by `docker-compose up -d`.

#### Pydantic Logfire (Observability)

```bash
# Optional: Add structured logging and tracing
# Get your token from <https://logfire.pydantic.dev>
LOGFIRE_TOKEN=your_logfire_token_here
```

**Recommended for:** Debugging, monitoring AI agent traces, and production observability.

**Free tier:** Logfire offers a generous free tier suitable for development.

#### AI Model Configuration

```bash
# AI model selection (defaults to Claude 3.5 Sonnet)
MODEL_ID=anthropic/claude-3.5-sonnet
```

Other options include `openai/gpt-4-turbo`, `google/gemini-pro`, etc. See
[OpenRouter models](<https://openrouter.ai/models>).

#### Admin Notification Configuration

```bash
# Enable/disable admin notifications for critical errors
ENABLE_ADMIN_NOTIFICATIONS=true

# Cooldown period between notifications (in minutes)
ADMIN_NOTIFICATION_COOLDOWN_MINUTES=60
```

Admin notifications help you stay informed of errors without being spammed.

## Step 3: Validate Configuration

After setting environment variables, validate that all required values are present:

```bash
# The application will validate on startup
# For now, check that critical variables are set:
grep -E "OPENROUTER_API_KEY|HOUSE_CODE|HOUSE_PASSWORD|POCKETBASE_ADMIN_" .env
```

**Expected output:** Each variable should have a non-empty value.

**Error:** If a required variable is missing or empty, the application will fail to start with a
clear error message:

- `OPENROUTER_API_KEY credential not configured`
- `House onboarding code credential not configured`
- `PocketBase admin email credential not configured`

## PocketBase Setup

### Starting PocketBase

PocketBase serves as the database backend. Start it:

```bash
# Option 1: Use the task (recommended)
task dev

# Option 2: Start manually
./pocketbase serve
```

PocketBase will start on <http://127.0.0.1:8090>

### Creating Admin Account

The application syncs the database schema on startup using the admin credentials configured in
`.env`. However, you need to create the admin account first.

#### Method 1: Automatic (via Task)

The `task dev` command automatically creates an admin account using the credentials from your
`.env` file.

#### Method 2: Manual (via Web UI)

1. Open <http://127.0.0.1:8090/_/> in your browser
2. Click "Create an admin account"
3. Enter the email and password from your `.env` file:
   - Email: `admin@example.com` (or whatever you set)
   - Password: `your_secure_admin_password` (or whatever you set)
4. Click "Create"

### Accessing Admin UI

The PocketBase Admin UI provides a web-based interface to view and manage data:

```bash
# Admin UI URL
open http://127.0.0.1:8090/_/
```

Use the admin credentials from your `.env` file to log in.

### Error: Admin account already exists

If you see "Admin account already exists" when creating via web UI:

1. Verify the credentials in `.env` match the existing admin
2. Or use PocketBase's superuser upsert command:

   ```bash
   ./pocketbase superuser upsert admin@example.com your_admin_password
   ```

### Verifying PocketBase Health

Check that PocketBase is running and accessible:

```bash
curl http://127.0.0.1:8090/api/health
```

**Expected output:** `{"status":"ok"}`

### Error: Connection refused or curl: (7) Failed to connect

**Solution:**

1. Check PocketBase is running: `ps aux | grep pocketbase`
2. Check port is available: `lsof -i :8090`
3. Check logs: `tail -f pocketbase.log` (if using task dev)

## WAHA Setup

WAHA provides the WhatsApp integration through a web interface.

### Starting WAHA

WAHA runs in Docker and should already be running from `docker-compose up -d`.

### Accessing WAHA Dashboard

1. Open <http://127.0.0.1:3000> in your browser
2. Click "Connect" or "Scan QR Code"
3. Use your WhatsApp app to scan the displayed QR code

### Verifying WAHA Connection

After scanning the QR code, WAHA should show your connected account and recent messages.

### Error: WAHA dashboard won't load

**Solution:**

1. Check container is running: `docker ps | grep waha`
2. Check container logs: `docker-compose logs waha`
3. Restart container: `docker-compose restart waha`

## Configuration Summary

After completing configuration, you should have:

- [ ] `.env` file with all required variables set
- [ ] PocketBase running on <http://127.0.0.1:8090>
- [ ] Redis running on localhost:6379
- [ ] WAHA running on <http://127.0.0.1:3000>
- [ ] PocketBase admin account created
- [ ] WAHA QR code scanned and WhatsApp connected

## Next Steps

Configuration complete! Continue to [First Run](./first-run.md) to start the application and send
your first message.

## Troubleshooting

### Environment variables not loading

**Error:** Application fails to read environment variables from `.env`

**Solution:**

1. Verify `.env` file exists in project root
2. Check file name is exactly `.env` (not `.env.txt` or `env`)
3. Ensure no syntax errors (no spaces around `=` for values)
4. Restart services to reload environment variables

### PocketBase schema sync fails

**Error:** Application fails to start with schema sync error

**Solution:**

1. Verify admin credentials in `.env` are correct
2. Check PocketBase is running and accessible
3. Delete `pb_data/` directory and restart (schema will sync from scratch):

   ```bash
   rm -rf pb_data
   ./pocketbase serve
   ```

### OpenRouter API key rejected

**Error:** `Invalid API key` or `Authentication failed`

**Solution:**

1. Verify API key starts with `sk-or-v1-`
2. Check you have credits in your OpenRouter account
3. Regenerate key if necessary at <https://openrouter.ai/keys>

### WAHA can't connect to WhatsApp

**Error:** QR code scan fails or connection drops

**Solution:**

1. Ensure stable internet connection
2. Use a fresh WhatsApp session (log out of other sessions if needed)
3. Try scanning QR code within 60 seconds (it expires)
4. Check WAHA logs: `docker-compose logs waha`

### Redis connection fails

**Error:** `Error connecting to Redis` or `Connection refused`

**Solution:**

1. Check Redis container is running: `docker ps | grep redis`
2. Verify URL in `.env`: `REDIS_URL=redis://localhost:6379`
3. Test Redis connection:

   ```bash
   docker-compose exec redis redis-cli ping
   ```

   Expected output: `PONG`

### Wrong house code/password

**Error:** User can't join household with message "Invalid credentials"

**Solution:**

1. Verify user sent the correct `HOUSE_CODE`
2. Verify user provided the correct `HOUSE_PASSWORD`
3. Check these values match exactly (case-sensitive)
4. Share credentials securely with household members

### Multiple instances conflicting

**Error:** Port already in use (8090, 6379, 3000, or 8000)

**Solution:**

1. Stop other instances of services
2. Use `task down` to stop all services
3. Check ports:

   ```bash
   lsof -i :8090  # PocketBase
   lsof -i :6379  # Redis
   lsof -i :3000  # WAHA
   lsof -i :8000  # FastAPI
   ```

4. Kill processes blocking ports: `kill -9 <PID>`
