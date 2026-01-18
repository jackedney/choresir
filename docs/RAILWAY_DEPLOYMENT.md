# Railway Deployment Guide

Deploy choresir to Railway for production use.

**Cost:** ~$5-10/month for both services

## Prerequisites

- GitHub repository with code
- Twilio WhatsApp tokens
- OpenRouter API key
- Railway account ([railway.app](https://railway.app))

## 1. Create Project

1. Go to [railway.app](https://railway.app)
2. Sign in with GitHub
3. Create **New Project** → **Empty Project**
4. Name: `choresir-production`

## 2. Deploy PocketBase

### Add Service

1. Click **+ New** → **Empty Service**
2. Name: `pocketbase`

### Configure

**Settings:**
- **Builder**: Dockerfile
- **Dockerfile Path**: `Dockerfile.pocketbase` (deploys PocketBase v0.23.6)

**Add Volume:**
1. Go to **Settings** → **Volumes**
2. **+ New Volume**
   - **Mount Path**: `/pb_data`
   - **Name**: `pocketbase_data`

### Deploy

1. **Settings** → **Source** → **Connect Repo**
2. Select your GitHub repository
3. Branch: `master`
4. Wait for deployment (~2-3 minutes)

### Verify

Check **Deployments** tab for green checkmark and logs showing:
```
Server started at http://0.0.0.0:8090
```

## 3. Deploy FastAPI

### Add Service

1. Click **+ New** → **GitHub Repo**
2. Select your repository
3. Name: `choresir-api`

### Add Environment Variables

Go to **Variables** tab and add:

```bash
# PocketBase (use private network)
POCKETBASE_URL=http://pocketbase.railway.internal:8090
POCKETBASE_ADMIN_EMAIL=<your admin email>
POCKETBASE_ADMIN_PASSWORD=<your admin password>

# OpenRouter
OPENROUTER_API_KEY=<your key>

# Twilio WhatsApp
WHATSAPP_VERIFY_TOKEN=<your token>
WHATSAPP_APP_SECRET=<your secret>
WHATSAPP_ACCESS_TOKEN=<your token>
WHATSAPP_PHONE_NUMBER_ID=<your id>

# House
HOUSE_CODE=<your code>
HOUSE_PASSWORD=<your password>

# Optional
MODEL_ID=anthropic/claude-3.5-sonnet
LOGFIRE_TOKEN=<your token>
```

### Generate Public Domain

1. **Settings** → **Networking** → **Generate Domain**
2. Copy URL (e.g., `choresir-api-production.up.railway.app`)

### Verify

Test health endpoint:
```bash
curl https://choresir-api-production.up.railway.app/health
```

## 4. Add Redis Cache

### Add Redis Plugin

1. In your Railway project, click **+ New**
2. Select **Database** → **Add Redis**
3. Railway will create a Redis service named `redis`

### Auto-Configuration

Railway automatically provides these environment variables to all services in the project:

```bash
REDIS_URL=redis://default:password@redis.railway.internal:6379
REDIS_PRIVATE_URL=redis://default:password@redis.railway.internal:6379
REDIS_PUBLIC_URL=redis://default:password@host.railway.app:port
```

The FastAPI application will automatically detect and use `REDIS_URL` for caching.

### Manual Configuration (if needed)

If the auto-configuration doesn't work, add to FastAPI service variables:

```bash
REDIS_URL=${{redis.REDIS_PRIVATE_URL}}
```

This creates a reference to the Redis service's private URL.

### Verify Redis Connection

1. Check FastAPI deployment logs for:
   ```
   Redis cache initialized successfully
   ```

2. Test cache endpoint:
   ```bash
   curl https://choresir-api-production.up.railway.app/health
   ```

   Look for `redis_connected: true` in the response.

3. If connection fails, check:
   - Redis service is deployed (green status)
   - `REDIS_URL` variable exists in FastAPI service
   - Logs show connection errors

### Redis Usage

The application uses Redis for:
- Caching verification listings (reduces database queries)
- Session management
- Rate limiting (if configured)

Cache automatically expires after configured TTL (default: 5 minutes).

## 5. Configure Twilio WhatsApp Webhook

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to **Messaging** → **Try it out** → **Send a WhatsApp message**
3. Configure webhook for your WhatsApp sender:
   - **When a message comes in**: `https://choresir-api-production.up.railway.app/webhook`
   - **Verify Token**: (from your `.env`)
4. Save configuration
5. Test by sending WhatsApp message to your Twilio number

## 6. Create Admin User

### Option 1: Via WhatsApp

Send to bot:
```
Join HOUSE123 SecretPass YourName
```

Access PocketBase admin:
1. **pocketbase service** → **Settings** → **Networking** → **Generate Domain**
2. Open URL in browser
3. Navigate to **Collections** → **users**
4. Edit your user: set `role` to "admin", `status` to "active"

### Option 2: Create Manually

1. Generate public domain for PocketBase
2. Open PocketBase admin UI
3. **Collections** → **users** → **New Record**
4. Set: `phone`, `name`, `role: admin`, `status: active`

## Verification Checklist

- [ ] PocketBase service healthy (green in Railway)
- [ ] PocketBase has persistent volume mounted
- [ ] Redis service healthy (green in Railway)
- [ ] FastAPI service healthy
- [ ] Health endpoint returns 200
- [ ] Redis connection verified (`redis_connected: true`)
- [ ] WhatsApp webhook verified (green checkmark)
- [ ] Test message gets reply
- [ ] Admin user exists
- [ ] Logfire shows traces (if configured)

## Maintenance

### Automatic Deployments

Railway auto-redeploys on push to GitHub `master` branch.

### Manual Redeploy

**Deployments** tab → **...** → **Redeploy**

### View Logs

Click service → **Deployments** → Latest → **View Logs**

### Backups

PocketBase data volume snapshots available on Railway Pro plan.

## Cost Breakdown

**Railway Hobby Plan ($5/month base):**
- PocketBase: ~$2-3/month
- Redis: ~$1-2/month
- FastAPI: ~$3-5/month
- **Total**: ~$6-10/month

**External Services:**
- OpenRouter: ~$3/month
- Twilio WhatsApp: Free (<1,000 conversations/month)
- Logfire: Free or $20/month

**Total Monthly: ~$9-33**

## Troubleshooting

**PocketBase data lost on redeploy:**
Ensure volume is mounted at `/pb_data` in service settings.

**FastAPI can't connect to PocketBase:**
Verify `POCKETBASE_URL` uses `http://pocketbase.railway.internal:8090` (not public URL).

**Webhook verification fails:**
Check `WHATSAPP_VERIFY_TOKEN` matches exactly in both Railway and Twilio Console. Redeploy after changing env vars.

**Messages not sending:**
- Check `WHATSAPP_ACCESS_TOKEN` is valid in Twilio Console
- Verify `WHATSAPP_PHONE_NUMBER_ID` matches your Twilio WhatsApp sender
- Check Railway logs for errors

**Redis connection failed:**
- Verify Redis service is deployed and healthy (green status)
- Check `REDIS_URL` variable exists in FastAPI service variables
- Ensure using private URL (`redis.railway.internal`) not public URL
- Restart FastAPI service after adding Redis

## Security

- [ ] Never commit `.env` to Git
- [ ] Use strong `HOUSE_PASSWORD`
- [ ] Enable 2FA on Railway account
- [ ] Remove PocketBase public domain after setup
- [ ] Monitor logs for suspicious activity

## Railway CLI (Optional)

```bash
# Install
npm install -g @railway/cli

# Login
railway login

# View logs
railway logs

# Deploy
railway up
```

## Configuration Files

Railway uses these files from your repo:

**`railway.toml`** (FastAPI):
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uv run fastapi run src/main.py --port $PORT"
healthcheckPath = "/health"
```

**`railway.pocketbase.toml`** (PocketBase):
```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile.pocketbase"

[deploy]
healthcheckPath = "/api/health"
```
