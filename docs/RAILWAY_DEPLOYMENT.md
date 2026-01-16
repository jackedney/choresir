# Railway Deployment Guide

Deploy choresir to Railway for production use.

**Cost:** ~$5-10/month for both services

## Prerequisites

- GitHub repository with code
- WhatsApp tokens
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
- **Dockerfile Path**: `Dockerfile.pocketbase`

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

# WhatsApp
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

## 4. Configure WhatsApp Webhook

1. Go to [Meta Developer Console](https://developers.facebook.com)
2. Navigate to **WhatsApp** → **Configuration**
3. Edit webhook:
   - **Callback URL**: `https://choresir-api-production.up.railway.app/webhook`
   - **Verify Token**: (from your `.env`)
4. Subscribe to **messages** events
5. Test by sending WhatsApp message

## 5. Create Admin User

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
- [ ] FastAPI service healthy
- [ ] Health endpoint returns 200
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
- FastAPI: ~$3-5/month
- **Total**: ~$5-8/month

**External Services:**
- OpenRouter: ~$3/month
- WhatsApp: Free (<1,000 conversations/month)
- Logfire: Free or $20/month

**Total Monthly: ~$8-31**

## Troubleshooting

**PocketBase data lost on redeploy:**
Ensure volume is mounted at `/pb_data` in service settings.

**FastAPI can't connect to PocketBase:**
Verify `POCKETBASE_URL` uses `http://pocketbase.railway.internal:8090` (not public URL).

**Webhook verification fails:**
Check `WHATSAPP_VERIFY_TOKEN` matches exactly. Redeploy after changing env vars.

**Messages not sending:**
- Check `WHATSAPP_ACCESS_TOKEN` is valid
- Verify `WHATSAPP_PHONE_NUMBER_ID` is correct
- Check Railway logs for errors

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
