# choresir 🏠

<p align="center">
  <img src="logo.png" width="200" alt="choresir logo">
</p>

**The "Household Operating System" that lives in WhatsApp.**

> **Status:** Active Development
> **Stack:** Python (FastAPI) | PocketBase | Pydantic AI | WhatsApp Cloud API

choresir is not just a reminder bot. It is an agentic system designed to manage household chores, enforce accountability, and resolve disputes through natural language. It replaces the "mental load" of managing a home with a neutral, AI-driven third party.

## 📚 Documentation

### For Users & Architects
*   **[Architecture Decisions](./adrs/):** The "Why" behind the system (Stack, Conflict Resolution, etc.).
*   **[Agent Personas](./adrs/002-agents.md):** Functional specifications for the `choresir` agent.

### For Developers & AI Assistants
*   **[Contribution Guide](./AGENTS.md):** Coding standards, engineering patterns, and the "System Prompt" for this repo. **Read this before writing code.**

## ✨ Features
*   **🛡️ Gatekeeper Onboarding:** "Join HOUSE123" + Admin Approval prevents strangers from spamming.
*   **🗣️ Conversational Config:** "Remind Alice to water the plants every Tuesday." (No forms, just text).
*   **✅ Verified Accountability:** When you say "I did the dishes," the bot asks someone else to verify it.
*   **🏹 The "Robin Hood" Protocol:** Swap chores dynamically. If you do someone else's task, you get the points.
*   **⚖️ Conflict Resolution:** A "Jury System" for disputes. If User A claims "Done" and User B rejects it, the bot triggers a vote.

## 🛠️ Tech Stack (The "Astral" Stack)
Optimized for low cost, high performance, and strictly typed Python.

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Server** | Python (FastAPI) | Core logic & Webhook receiver. |
| **Tooling** | **uv, ruff, ty** | Blazing fast package management, linting, and type checking. |
| **Agent** | Pydantic AI | Strongly-typed AI logic & tool calling. |
| **Observability** | **Logfire** | Structured tracing for AI & API. |
| **Database** | PocketBase | Self-hosted SQLite backend + Admin UI. |
| **Interface** | WhatsApp Cloud API | Direct integration (No Twilio markup). |

## 🚀 Getting Started

### Quick Start (Already Have Accounts)
If you already have Meta/WhatsApp, OpenRouter, and the code:
**→ [Quick Start Guide](./docs/QUICK_START.md)** (15-30 minutes)

### First Time Setup (Complete Walkthrough)
If starting from scratch:
**→ [Complete Setup Guide](./docs/SETUP.md)** (2-3 hours + waiting for approvals)

### Setup by Component

| Component | Guide | Time | Status |
|-----------|-------|------|--------|
| **WhatsApp Templates** | [WHATSAPP_TEMPLATES.md](./docs/WHATSAPP_TEMPLATES.md) | 30 min + 1-2 days approval | Required for >24h messages |
| **ngrok (Local Testing)** | [NGROK_SETUP.md](./docs/NGROK_SETUP.md) | 15 min | Required for local webhook testing |
| **Logfire (Monitoring)** | [LOGFIRE_SETUP.md](./docs/LOGFIRE_SETUP.md) | 10 min | Optional but recommended |
| **Railway (Production)** | [RAILWAY_DEPLOYMENT.md](./docs/RAILWAY_DEPLOYMENT.md) | 1 hour | For production deployment |

### Minimal Local Setup (5 minutes)

```bash
# Install dependencies
uv sync

# Download PocketBase
task setup

# Configure environment
cp .env.example .env
# Edit .env with your tokens

# Start services (3 terminals)
./pocketbase serve                    # Terminal 1
uv run fastapi dev src/main.py        # Terminal 2
ngrok http 8000                       # Terminal 3
```

See [Quick Start Guide](./docs/QUICK_START.md) for detailed instructions.

## ☁️ Production Deployment

**Platform:** Railway (recommended)
**Cost:** ~$5-10/month
**Guide:** [docs/RAILWAY_DEPLOYMENT.md](./docs/RAILWAY_DEPLOYMENT.md)

**Quick deploy:**
1. Create Railway project
2. Deploy PocketBase service (with persistent volume)
3. Deploy FastAPI service (connect GitHub repo)
4. Set environment variables
5. Update WhatsApp webhook URL

Full automation options available in [Infrastructure as Code guide](./docs/INFRASTRUCTURE_AS_CODE.md).
