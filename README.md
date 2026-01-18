<div align="center">

<img src="assets/images/hero-banner.png" alt="Minimalist neobrutalist illustration of a house with a robot face and a single speech bubble on a clean background" width="100%">

### The Household Operating System that lives in WhatsApp

<p align="center">
  <img src="https://img.shields.io/badge/status-active%20development-green?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/python-3.12+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/WhatsApp-25D366?style=for-the-badge&logo=whatsapp&logoColor=white" alt="WhatsApp">
  <img src="https://img.shields.io/badge/Logfire-FF6B6B?style=for-the-badge" alt="Logfire">
  <img src="https://img.shields.io/badge/uv-DE5FE9?style=for-the-badge&logo=astral&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/Ruff-FCC21B?style=for-the-badge&logo=ruff&logoColor=black" alt="Ruff">
</p>

---

**choresir** is not just a reminder bot. It's an agentic system designed to manage household chores, enforce accountability, and resolve disputes through natural language. It replaces the "mental load" of managing a home with a neutral, AI-driven third party.

</div>

## 📚 Documentation

<table>
<tr>
<td width="50%">

### 👥 For Users & Architects
- 📐 **[Architecture Decisions](./adrs/)** - The "Why" behind the system
- 🤖 **[Agent Personas](./adrs/002-agents.md)** - Functional specifications

</td>
<td width="50%">

### 💻 For Developers & AI Assistants
- 📝 **[Contribution Guide](./AGENTS.md)** - Coding standards & patterns
  *Read this before writing code*

</td>
</tr>
</table>

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🛡️ **Gatekeeper Onboarding** | "Join HOUSE123" + Admin Approval prevents strangers from spamming |
| 🗣️ **Conversational Config** | "Remind Alice to water the plants every Tuesday." (No forms, just text) |
| ✅ **Verified Accountability** | When you say "I did the dishes," the bot sends a message with [✅ Approve] [❌ Reject] buttons to household members |
| 🏹 **The "Robin Hood" Protocol** | Swap chores dynamically. If you do someone else's task, you get the points |
| ⚖️ **Conflict Resolution** | A "Jury System" for disputes. If User A claims "Done" and User B rejects it, the bot triggers a vote |

## 🛠️ Tech Stack

<div align="center">

*Optimized for low cost, high performance, and strictly typed Python*

</div>

<table>
<thead>
<tr>
<th width="25%">Component</th>
<th width="35%">Technology</th>
<th width="40%">Role</th>
</tr>
</thead>
<tbody>
<tr>
<td>🖥️ <strong>Server</strong></td>
<td><img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI"></td>
<td>Core logic & Webhook receiver</td>
</tr>
<tr>
<td>🔧 <strong>Tooling</strong></td>
<td><strong>uv, ruff, ty</strong></td>
<td>Blazing fast package management, linting, and type checking</td>
</tr>
<tr>
<td>🤖 <strong>Agent</strong></td>
<td><img src="https://img.shields.io/badge/Pydantic_AI-E92063?style=flat&logo=pydantic&logoColor=white" alt="Pydantic AI"></td>
<td>Strongly-typed AI logic & tool calling</td>
</tr>
<tr>
<td>📊 <strong>Observability</strong></td>
<td><strong>Logfire</strong></td>
<td>Structured tracing for AI & API</td>
</tr>
<tr>
<td>💾 <strong>Database</strong></td>
<td><img src="https://img.shields.io/badge/PocketBase-B8DBE4?style=flat&logo=pocketbase&logoColor=black" alt="PocketBase"></td>
<td>Self-hosted SQLite backend + Admin UI</td>
</tr>
<tr>
<td>⚡ <strong>Cache</strong></td>
<td><img src="https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white" alt="Redis"></td>
<td>High-performance caching for leaderboards & analytics</td>
</tr>
<tr>
<td>💬 <strong>Interface</strong></td>
<td><img src="https://img.shields.io/badge/WhatsApp_Cloud_API-25D366?style=flat&logo=whatsapp&logoColor=white" alt="WhatsApp"></td>
<td>Direct integration (No Twilio markup)</td>
</tr>
</tbody>
</table>

## 🚀 Getting Started

<div align="center">
</div>

<table>
<tr>
<td width="80%">

### ⚡ Quick Start
*Already have Meta/WhatsApp & OpenRouter accounts?*

**→ [Quick Start Guide](./docs/QUICK_START.md)**

**Required Accounts:**
- [OpenRouter](https://openrouter.ai) - AI model access (~$3/month)
- [Meta Developer](https://developers.facebook.com) - WhatsApp API (free)
- [ngrok](https://ngrok.com) - Local webhook tunnel (free)

</td>
<td width="50%">

### 🔰 First Time Setup
*Starting from scratch?*

**→ [Complete Setup Guide](./docs/SETUP.md)**

</td>
</tr>
</table>

### 📦 Setup by Component

<table>
<thead>
<tr>
<th width="40%">Component</th>
<th width="40%">Guide</th>
<th width="20%">Status</th>
</tr>
</thead>
<tbody>
<tr>
<td>💬 <strong>WhatsApp Templates</strong></td>
<td><a href="./docs/WHATSAPP_TEMPLATES.md">WHATSAPP_TEMPLATES.md</a></td>
<td><img src="https://img.shields.io/badge/required-red?style=flat" alt="Required"></td>
</tr>
<tr>
<td>🌐 <strong>ngrok (Local Testing)</strong></td>
<td><a href="./docs/NGROK_SETUP.md">NGROK_SETUP.md</a></td>
<td><img src="https://img.shields.io/badge/required-red?style=flat" alt="Required"></td>
</tr>
<tr>
<td>📊 <strong>Logfire (Monitoring)</strong></td>
<td><a href="./docs/LOGFIRE_SETUP.md">LOGFIRE_SETUP.md</a></td>
<td><img src="https://img.shields.io/badge/recommended-orange?style=flat" alt="Recommended"></td>
</tr>
<tr>
<td>🚂 <strong>Railway (Production)</strong></td>
<td><a href="./docs/RAILWAY_DEPLOYMENT.md">RAILWAY_DEPLOYMENT.md</a></td>
<td><img src="https://img.shields.io/badge/production-blue?style=flat" alt="Production"></td>
</tr>
</tbody>
</table>

### 💻 Minimal Local Setup

```bash
# 1️⃣ Install dependencies
uv sync

# 2️⃣ Download PocketBase
task setup

# 3️⃣ Start Redis (choose one method):
# Option A: Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Option B: Docker Compose
docker-compose up -d redis

# Option C: Local installation
# macOS: brew install redis && brew services start redis
# Linux: sudo apt-get install redis-server && sudo systemctl start redis

# 4️⃣ Configure environment
cp .env.example .env
# Edit .env with your tokens (OpenRouter API key, WhatsApp credentials, etc.)

# 5️⃣ Start services (requires 3 terminals)
./pocketbase serve                    # Terminal 1: Database
uv run fastapi dev src/main.py        # Terminal 2: API Server
ngrok http 8000                       # Terminal 3: Public Webhook
```

<div align="center">

📖 **See [Quick Start Guide](./docs/QUICK_START.md) for detailed instructions**

</div>

## ☁️ Production Deployment

<table>
<tr>
<td width="80%">

### 🚂 Railway Deployment

**Platform:** Railway (recommended)
**Cost:** ~$5-10/month
**Guide:** [RAILWAY_DEPLOYMENT.md](./docs/RAILWAY_DEPLOYMENT.md)

#### Quick Deploy Steps:
1. ✅ Create Railway project
2. 💾 Deploy PocketBase service (with persistent volume)
3. ⚡ Add Redis plugin (for caching)
4. 🖥️ Deploy FastAPI service (connect GitHub repo)
5. 🔐 Set environment variables (including REDIS_URL)
6. 🔗 Update WhatsApp webhook URL

</td>
<td width="40%">

<div align="center">

### Cost Breakdown

| Service | Monthly Cost |
|---------|--------------|
| PocketBase | ~$3-5 |
| Redis | ~$1-3 |
| FastAPI | ~$2-5 |
| **Total** | **$6-13** |

</div>

</td>
</tr>
</table>

---

<div align="center">

<img src="assets/images/whatsapp-integration.png" alt="Stylized smartphone icon featuring the WhatsApp logo and small chore notification bubbles" width="200">

### 🎯 Ready to transform your household management?

**[Get Started Now](./docs/QUICK_START.md)** | **[Read the Docs](./adrs/)** | **[View Architecture](./AGENTS.md)**

---

<sub>Built with ❤️ | MIT License</sub>

</div>
