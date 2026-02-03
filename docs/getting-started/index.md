# Getting Started

Welcome to the WhatsApp Home Boss getting started guide. This section will help you set up
and run the application on your local machine.

## Overview

WhatsApp Home Boss is a household operating system that lives in WhatsApp. It uses AI to
manage chores, enforce accountability, and resolve disputes through natural language.

### Key Components

| Component | Purpose | Runs On |
| ----------- | --------- | ---------- |
| PocketBase | Self-hosted database | <http://127.0.0.1:8090> |
| Redis | Caching layer for leaderboards | localhost:6379 |
| WAHA | WhatsApp integration (self-hosted) | <http://127.0.0.1:3000> |
| FastAPI | Application server and webhook handler | <http://localhost:8000> |

### What You'll Need

- Python 3.12+ - Application runtime
- uv - Fast Python package manager
- Docker & Docker Compose - For Redis and WAHA
- OpenRouter API Key - For AI agent access (~$0.10/day)
- WhatsApp Phone - To connect via WAHA

## Setup Steps

Follow these guides in order to get up and running:

### 1. [Installation](./installation.md)

Install all required dependencies including:

- Python packages via `uv`
- PocketBase binary
- Docker services (Redis, WAHA)

**Time:** 10-15 minutes

### 2. [Configuration](./configuration.md)

Configure the application by setting up:

- Environment variables (.env file)
- PocketBase admin account
- WAHA connection to WhatsApp
- OpenRouter API key

**Time:** 5-10 minutes

### 3. [First Run](./first-run.md)

Start the application and verify everything works:

- Start all services (PocketBase, FastAPI, Redis, WAHA)
- Create your admin user
- Send your first message to the bot
- Verify connection and responses

**Time:** 5-10 minutes

## Quick Start Summary

If you're comfortable with command-line tools, here's the condensed version:

```bash
# 1. Install dependencies
uv sync

# 2. Download PocketBase
task install-pocketbase

# 3. Start Docker services
docker-compose up -d

# 4. Configure environment
cp .env.example .env
# Edit .env with your tokens and credentials

# 5. Start all services
task dev

# 6. Scan WAHA QR code
# Open <http://127.0.0.1:3000> in your browser
# Scan the QR code with WhatsApp

# 7. Create admin user
# Send "Join HOUSE123 YourPass YourName" to your WhatsApp

# 8. Verify setup
# Send "Hello" to the bot and check for a response
```

## Troubleshooting

If you encounter issues during setup:

- Installation problems - See [Installation Troubleshooting](./installation.md#troubleshooting)
- Configuration issues - See [Configuration Troubleshooting](./configuration.md#troubleshooting)
- First run problems - See [First Run Troubleshooting](./first-run.md#common-issues)

### Common Issues

#### PocketBase fails to start

- Check port 8090 is available: `lsof -i :8090`
- Verify binary is executable: `chmod +x pocketbase`

#### Docker services won't start

- Check Docker is running: `docker ps`
- View container logs: `docker-compose logs`

#### Bot doesn't respond

- Verify user is approved in PocketBase (`status: active`)
- Check OpenRouter API key has credits
- Review FastAPI logs for errors

## Next Steps

After completing setup:

- [User Guide](../user-guide/index.md) - Learn about all features and commands
- [Architecture Documentation](../architecture/index.md) - Understand how the system works
- [Contributors Guide](../contributors/index.md) - Learn how to contribute

## Getting Help

If you need additional help:

1. Check the [Troubleshooting](#troubleshooting) section in each guide
2. Review [Architecture Documentation](../architecture/index.md) to understand the system
3. Check logs:

   - FastAPI: `fastapi.log` (or terminal output)
   - PocketBase: `pocketbase.log` (or terminal output)
   - WAHA: `docker-compose logs waha`
   - Redis: `docker-compose logs redis`

## Prerequisites Checklist

Before starting installation, verify you have:

- [ ] Python 3.12 or later installed
- [ ] `uv` package manager installed
- [ ] Git installed
- [ ] Docker installed and running
- [ ] Docker Compose installed
- [ ] ngrok installed (for webhook tunneling, optional)
- [ ] OpenRouter account with API key
- [ ] WhatsApp app ready to scan QR code

Run the quick check:

```bash
python --version  # Should be 3.12+
uv --version
docker --version
docker-compose --version
git --version
```

All commands should complete without errors.
