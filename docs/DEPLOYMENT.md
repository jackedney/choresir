# Deployment Guide

## Railway Deployment

This application deploys as two separate services on Railway:

1. **PocketBase Service**: Database backend
2. **FastAPI Worker**: Application server

### Prerequisites

- Railway account
- GitHub repository connected to Railway
- Environment variables configured

### Service 1: PocketBase

**Configuration:**
- Uses `Dockerfile.pocketbase` for deployment
- Mounts persistent volume at `/pb_data`
- Health check endpoint: `/api/health`
- Internal port: 8090

**Setup:**
1. Create new service in Railway
2. Deploy from Dockerfile: `Dockerfile.pocketbase`
3. Add volume mount: `/pb_data` → `pocketbase_data`
4. Note the internal service URL format: `http://<service-name>.railway.internal:<port>`
   - Example: `http://pocketbase.railway.internal:8090`
   - Alternative using reference variables: `http://${{pocketbase.RAILWAY_PRIVATE_DOMAIN}}:8090`

### Service 2: FastAPI Worker

**Configuration:**
- Uses `railway.toml` for deployment
- Build command: `uv sync`
- Start command: `uv run fastapi run src/main.py --port $PORT`
- Health check endpoint: `/health`

**Required Environment Variables:**
```
# Option 1: Direct service name reference
POCKETBASE_URL=http://pocketbase.railway.internal:8090

# Option 2: Using Railway reference variables (recommended)
POCKETBASE_URL=http://${{pocketbase.RAILWAY_PRIVATE_DOMAIN}}:8090

# Other required variables
OPENROUTER_API_KEY=<your-key>
TWILIO_ACCOUNT_SID=<your-sid>
TWILIO_AUTH_TOKEN=<your-token>
TWILIO_WHATSAPP_NUMBER=<your-number>
LOGFIRE_TOKEN=<your-token>
HOUSE_CODE=<your-code>
HOUSE_PASSWORD=<your-password>
MODEL_ID=anthropic/claude-3.5-sonnet (optional)
```

**Note:** When using reference variables, ensure the service name matches exactly (e.g., `pocketbase`). Private networking uses HTTP (not HTTPS) for internal communication.

**Setup:**
1. Create new service in Railway
2. Connect to GitHub repository
3. Set environment variables in Railway dashboard
4. Deploy from `railway.toml`
5. Note the public URL for webhook configuration

### Post-Deployment

1. Configure WhatsApp webhook URL in Twilio Console
2. Go to Messaging → WhatsApp Sandbox → Sandbox Configuration
3. Set webhook URL to: `https://<your-railway-url>/webhook`
4. Set HTTP method to POST and save
5. Monitor logs in Railway dashboard
6. Check Logfire for application traces

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `POCKETBASE_URL` | Internal URL of PocketBase service | Yes |
| `OPENROUTER_API_KEY` | API key for OpenRouter LLM access | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | Yes |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number | Yes |
| `LOGFIRE_TOKEN` | Pydantic Logfire token for observability | Yes |
| `HOUSE_CODE` | Code for users to join household | Yes |
| `HOUSE_PASSWORD` | Password for users to join household | Yes |
| `MODEL_ID` | LLM model identifier (defaults to Claude 3.5 Sonnet) | No |

## Health Checks

- PocketBase: `GET /api/health`
- FastAPI: `GET /health`

## Monitoring

- View logs in Railway dashboard
- View traces in Pydantic Logfire dashboard
- Monitor WhatsApp webhook deliveries in Twilio Console
