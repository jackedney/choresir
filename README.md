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

**Full documentation available in MkDocs format.**

To build and view documentation locally:
```bash
mkdocs serve
```

Then visit `http://127.0.0.1:8000`

**Quick Links:**
- **[Getting Started](docs/getting-started/)** - Setup, installation, and first run
- **[Contributors](docs/contributors/)** - Development workflow, code quality, and patterns
- **[Architecture](docs/architecture/)** - System design and engineering patterns
- **[Agent Development](docs/agents/)** - Building and extending Pydantic AI agents
- **[User Guide](docs/user-guide/)** - Features and usage instructions

## ✨ Features

### Household Management
| Feature | Description |
|---------|-------------|
| 🛡️ **Gatekeeper Onboarding** | "Join HOUSE123" + Admin Approval prevents strangers from spamming |
| 🗣️ **Conversational Config** | "Remind Alice to water the plants every Tuesday." (No forms, just text) |
| ✅ **Verified Accountability** | When you say "I did the dishes," the bot sends a message with [✅ Approve] [❌ Reject] buttons to household members |
| 🏹 **The "Robin Hood" Protocol** | Swap chores dynamically. If you do someone else's task, you get the points |
| ⚖️ **Conflict Resolution** | A "Jury System" for disputes. If User A claims "Done" and User B rejects it, the bot triggers a vote |
| 📊 **Weekly Leaderboard** | Gamified chore completion tracking with weekly stats and analytics |
| 🛒 **Smart Pantry** | Inventory tracking and smart shopping list generation |

### Personal Chore Tracking 🆕
Track your personal tasks privately within the same WhatsApp interface:
- **🔒 Private by Default**: Only you can see your personal chores
- **🤝 Optional Accountability**: Assign household members to verify your completions
- **📅 Flexible Scheduling**: One-time tasks or recurring habits (supports "every morning", "by Friday", "every Monday", etc.)
- **🏠 Separate from Household**: Personal chores don't affect the household leaderboard

**Commands:**
```
/personal add <task> [recurrence] [accountability:@user]  # Create personal chore
/personal done <task>                                      # Log completion
/personal list                                             # View your chores
/personal stats                                            # View your statistics
/personal remove <task>                                    # Delete a chore
```

**Examples:**
```
/personal add gym every 2 days accountability:@Bob
/personal add finish report by Friday
/personal add meditate every morning
```

### Web Admin Interface 🆕

Manage your household through a modern web interface at `/admin`:
- **🔐 Secure Login**: Password-protected admin access (set `ADMIN_PASSWORD` in .env)
- **🏠 House Configuration**: Update house name, password, and code via web UI
- **👥 Member Management**: View, add, edit, and remove/ban household members
- **📱 WhatsApp Setup**: Connect WhatsApp, view QR code, and configure group chat mode
- **💬 Group Chat Mode**: Configure ChoresSir to respond in a house group instead of DMs
- **📊 Dashboard**: Quick overview of member counts and status
- **🎨 Responsive Design**: Works on desktop and mobile browsers

**Access:**
- Local: `http://localhost:8000/admin`
- Production: `https://your-domain.com/admin`

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
<td><img src="https://img.shields.io/badge/WhatsApp-25D366?style=flat&logo=whatsapp&logoColor=white" alt="WhatsApp"></td>
<td>WhatsApp via WAHA (Self-Hosted)</td>
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
*Already have OpenRouter account?*

**→ [Getting Started](docs/getting-started/)**

**Required Accounts:**
- [OpenRouter](https://openrouter.ai) - AI model access (~$3/month)

</td>
<td width="50%">

### 🔰 First Time Setup
*Starting from scratch?*

**→ [Getting Started](docs/getting-started/)**

</td>
</tr>
</table>

### 📦 Setup by Component

Detailed setup instructions are available in the [Getting Started](docs/getting-started/) documentation.

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
# Edit .env with your tokens (OpenRouter API key, etc.)
# IMPORTANT: Set ADMIN_PASSWORD to access the web admin interface

# 5️⃣ Start services
# Option A: Full Docker (Recommended)
docker-compose up -d

# Option B: Dev Mode
docker-compose up -d redis waha      # Start dependencies
task dev                             # Start PocketBase + FastAPI

# 6️⃣ Configure via Web Admin
# Open http://localhost:8000/admin and log in with ADMIN_PASSWORD
# - Set your house name in Settings
# - Go to WhatsApp Setup to connect WhatsApp and activate your group
```

<div align="center">

📖 **See [Getting Started](docs/getting-started/) for detailed instructions**

</div>

## ☁️ Production Deployment

<table>
<tr>
<td width="80%">

### 🐳 Docker Deployment

**Platform:** Docker Compose (any VPS or container platform)
**Cost:** ~$5-10/month (any VPS provider)
**Guide:** See [Getting Started > Production](docs/getting-started/) documentation

#### Quick Deploy Steps:
1. ✅ Clone the repository
2. 📝 Copy `.env.example` to `.env` and configure:
   - `ADMIN_PASSWORD`: Password for web admin interface access (required)
   - `SECRET_KEY`: Secret key for session signing (required, generate a random string)
   - `REDIS_URL`: Redis connection URL (required)
   - `OPENROUTER_API_KEY`: OpenRouter API key (required)
   - `HOUSE_NAME`: Optional fallback house name
3. 🚀 Run `docker-compose up -d`
4. 🔗 Update WhatsApp webhook URL to your server
5. 🌐 Access admin interface at `https://your-domain.com/admin`

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

**[Get Started Now](docs/getting-started/)** | **[Documentation](docs/)**

---

<sub>Built with ❤️ | MIT License</sub>

</div>
