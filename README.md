```
 ██████╗██╗  ██╗ ██████╗ ██████╗ ███████╗███████╗██╗██████╗
██╔════╝██║  ██║██╔═══██╗██╔══██╗██╔════╝██╔════╝██║██╔══██╗
██║     ███████║██║   ██║██████╔╝█████╗  ███████╗██║██████╔╝
██║     ██╔══██║██║   ██║██╔══██╗██╔══╝  ╚════██║██║██╔══██╗
╚██████╗██║  ██║╚██████╔╝██║  ██║███████╗███████║██║██║  ██║
 ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═╝
```

Household Operating System in WhatsApp. Agentic chore management with accountability.

---

## [!] WHAT IS THIS

Not a reminder bot. An AI-powered household manager that:
- Enforces accountability through verification workflows
- Resolves disputes with voting systems
- Tracks personal and shared tasks
- Lives entirely in WhatsApp

**No apps. No downloads. Just text.**

---

```
╔═══════════════════════════════════════════════════════════╗
║                         STACK                             ║
╚═══════════════════════════════════════════════════════════╝
```

- **Runtime**: Python 3.12+ | FastAPI
- **AI**: Pydantic AI | OpenRouter
- **Database**: SQLite (embedded, no server)
- **Tooling**: uv, ruff, ty
- **Interface**: WhatsApp (via WAHA)
- **Monitoring**: Logfire

---

```
╔═══════════════════════════════════════════════════════════╗
║                      QUICK START                          ║
╚═══════════════════════════════════════════════════════════╝
```

**Prerequisites:**
- OpenRouter account (~$3/month)
- WhatsApp Business API access (WAHA self-hosted)

**Install:**
```bash
uv sync
cp .env.example .env
# Edit .env with your credentials
```

**Run:**
```bash
# Full stack (recommended)
docker-compose up -d

# Dev mode
docker-compose up -d waha
task dev
```

**Configure:**
1. Open http://localhost:8000/admin
2. Login with ADMIN_PASSWORD from .env
3. Connect WhatsApp
4. Set house name and group chat

---

```
╔═══════════════════════════════════════════════════════════╗
║                       FEATURES                            ║
╚═══════════════════════════════════════════════════════════╝
```

**CORE:**
- Gatekeeper onboarding (join codes)
- Conversational config (no forms)
- Verified accountability (approval workflows)
- Robin Hood protocol (chore swapping)
- Conflict resolution (jury voting)
- Weekly leaderboard

**PERSONAL:**
- Private task tracking
- Optional accountability partners
- Flexible scheduling
- Auto-verification after 48h timeout

**ADMIN:**
- Web interface at /admin
- Member management
- WhatsApp setup & QR codes
- Group chat mode
- Configuration UI

---

```
╔═══════════════════════════════════════════════════════════╗
║                      DEPLOYMENT                           ║
╚═══════════════════════════════════════════════════════════╝
```

**Docker (any VPS):**
```bash
git clone <repo>
cp .env.example .env
# Configure .env
docker-compose up -d
```

**Cost:** $2-5/month VPS

**Required env vars:**
- `ADMIN_PASSWORD`: Web admin access
- `SECRET_KEY`: Session signing
- `OPENROUTER_API_KEY`: AI access

---

```
╔═══════════════════════════════════════════════════════════╗
║                         DOCS                              ║
╚═══════════════════════════════════════════════════════════╝
```

Run locally:
```bash
mkdocs serve
```

Browse to: http://127.0.0.1:8000

**Sections:**
- Getting Started: Setup & installation
- Contributors: Development workflow
- Architecture: System design
- Agents: AI development guide
- User Guide: Feature documentation

---

```
╔═══════════════════════════════════════════════════════════╗
║                       COMMANDS                            ║
╚═══════════════════════════════════════════════════════════╝
```

**Personal chores:**
```
/personal add <task> [recurrence] [accountability:@user]
/personal done <task>
/personal list
/personal stats
/personal remove <task>
```

**Examples:**
```
/personal add gym every 2 days accountability:@Bob
/personal add finish report by Friday
/personal add meditate every morning
```

---

MIT License | Built with uv + FastAPI + Pydantic AI
