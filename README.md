# choresir 🏠

<p align="center">
  <img src="logo.png" width="200" alt="choresir logo">
</p>

**The "Household Operating System" that lives in WhatsApp.**

> **Status:** Active Development
> **Stack:** Python (FastAPI) | PocketBase | Pydantic AI | Twilio WhatsApp API

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
| **Interface** | Twilio WhatsApp API | Reliable WhatsApp integration. |

## 🚀 Getting Started

### Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure environment variables:**
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. **Start all services:**
   ```bash
   task dev
   ```

   This automatically:
   - Installs PocketBase
   - Creates admin account
   - Starts FastAPI and ngrok
   - Shows you the webhook URL

4. **Configure webhook:**
   Copy the ngrok URL and set it in Twilio Console → Messaging → WhatsApp Sandbox.

### Full Setup Guide

See [SETUP.md](./docs/SETUP.md) for detailed instructions including:
- External service configuration (OpenRouter, Twilio, Logfire)
- Production deployment
- Webhook configuration

### Prerequisites
- **uv** (Python package manager) - [Install here](https://docs.astral.sh/uv/getting-started/installation/)
- **ngrok** (for local webhook testing) - `brew install ngrok`
- **Twilio Account** - For WhatsApp integration
- **OpenRouter API Key** - [Get here](https://openrouter.ai)

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

## 📖 Additional Documentation

- **[Local Development Guide](./docs/LOCAL_DEVELOPMENT.md)** - Detailed development workflow, debugging tips
- **[Setup Guide](./docs/SETUP.md)** - Complete external service configuration (OpenRouter, WhatsApp, Logfire)
- **[PocketBase Setup](./docs/POCKETBASE_SETUP.md)** - Database configuration details
- **[Twilio Migration](./docs/TWILIO_MIGRATION.md)** - Migration from Meta to Twilio
- **[Deployment Guide](./docs/DEPLOYMENT.md)** - Production deployment instructions
