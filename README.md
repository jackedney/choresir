# HomeBase 🏠

**The "Household Operating System" that lives in WhatsApp.**

> **Status:** Active Development  
> **Stack:** Python (FastAPI) | PocketBase | Pydantic AI | WhatsApp Cloud API

HomeBase is not just a reminder bot. It is an agentic system designed to manage household chores, enforce accountability, and resolve disputes through natural language. It replaces the "mental load" of managing a home with a neutral, AI-driven third party.

## 📚 Documentation
*   **[Architecture Decisions](./adrs/001-stack.md):** Why we chose the "Indie Stack."
*   **[Agent Specification](./AGENTS.md):** How the AI thinks and the tools it uses.

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

### Prerequisites
1.  **uv** (The Python package manager)
2.  PocketBase executable (v0.22+)
3.  Meta Developer Account (WhatsApp Product)
4.  OpenRouter API Key

### 1. Database Setup
1.  Start server: `./pocketbase serve`
2.  Go to `http://127.0.0.1:8090/_/` and create Admin account.
3.  Import schema from `pocketbase_schema.json`.

### 2. Environment Variables (`.env`)
```bash
POCKETBASE_URL="http://127.0.0.1:8090"
OPENROUTER_API_KEY="sk-or-..."
WHATSAPP_VERIFY_TOKEN="random_string"
LOGFIRE_TOKEN="your_token"
HOUSE_CODE="HOUSE123"
HOUSE_PASSWORD="SecretPass"
```

### 3. Run the Server
```bash
uv sync
uv run fastapi dev app/main.py
```

### 4. Connect WhatsApp (Localhost)
1.  `ngrok http 8000`
2.  Meta Developers -> Configuration -> Webhook URL: `https://xyz.ngrok-free.app/webhook`

## 📂 Project Structure (Service-Layered)
```text
.
├── app/
│   ├── agents/         # Pydantic AI Agents & Prompts
│   ├── api/            # FastAPI Routers (Webhooks, Admin)
│   ├── core/           # Config, Logging, Security
│   ├── models/         # Pydantic Data Models (Shared)
│   ├── services/       # Business Logic (Auditor, Jury, Ledger)
│   └── main.py         # App Entrypoint
├── tests/              # Pytest Suite (Ephemeral DB)
├── pyproject.toml      # uv Config
└── README.md

## ☁️ Deployment (Railway)
1.  **PocketBase Service:** Use the template + Attach Volume to `/pb_data`.
2.  **Python Worker:** Connect GitHub repo. Set `POCKETBASE_URL` to the internal service URL.