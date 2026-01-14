HomeBase 🏠

The "Household Operating System" that lives in WhatsApp.

    Status: Active Development Stack: Python (FastAPI) | PocketBase | Pydantic AI | WhatsApp Cloud API

HomeBase is not just a reminder bot. It is an agentic system designed to manage household chores, enforce accountability, and resolve disputes through natural language. It replaces the "mental load" of managing a home with a neutral, AI-driven third party.
📚 Documentation

    Architecture Decisions (ADRs): Why we chose this specific "Indie Stack."

    Agent Specification: How the AI thinks and the tools it uses.

✨ Features

    🗣️ Conversational Config: "Remind Alice to water the plants every Tuesday." (No forms, just text).

    ✅ Verified Accountability: When you say "I did the dishes," the bot asks someone else to verify it. No verification = no credit.

    🏹 The "Robin Hood" Protocol: Swap chores dynamically. If you do someone else's task, the bot reassigns credit and prompts for reciprocity.

    ⚖️ Conflict Resolution: A "Jury System" for disputes. If User A claims "Done" and User B rejects it, the bot triggers a vote among other members.

    ⏳ Automated Nagging: Escalating notifications from "Gentle Reminder" to "Public Shaming."

🛠️ Tech Stack

This project uses the "Indie Stack"—optimized for low cost, high maintainability, and single-developer velocity.
Component	Technology	Role
Server	Python (FastAPI)	The core logic and Webhook receiver.
Agent Framework	Pydantic AI	Strongly-typed AI logic & tool calling.
Intelligence	OpenRouter	Gateway to Claude 3.5 Sonnet (Model ID: anthropic/claude-3.5-sonnet).
Database	PocketBase	Self-hosted SQLite backend + Admin UI.
Interface	WhatsApp API	Meta's Cloud API for messaging.
🚀 Getting Started
Prerequisites

    Python 3.11+

    PocketBase (v0.22+) executable

    A Meta Developer Account (WhatsApp Product)

    An OpenRouter API Key

1. Database Setup

    Download the pocketbase executable.

    Start the server: ./pocketbase serve.

    Go to http://127.0.0.1:8090/_/ and create your Admin account.

    Import the schema:

        Settings -> Import Collections.

        Upload ./pocketbase_schema.json (Found in this repo).

2. Environment Variables

Create a .env file in the root directory:
Bash

# PocketBase
POCKETBASE_URL="http://127.0.0.1:8090"
POCKETBASE_ADMIN_EMAIL="admin@example.com"
POCKETBASE_ADMIN_PASSWORD="your-password"

# AI
OPENROUTER_API_KEY="sk-or-..."
MODEL_ID="anthropic/claude-3.5-sonnet"

# WhatsApp
WHATSAPP_VERIFY_TOKEN="random_string_you_create"
WHATSAPP_ACCESS_TOKEN="EAAG..."
WHATSAPP_PHONE_ID="123456789"

3. Run the Server

Install dependencies and run FastAPI:
Bash

pip install -r requirements.txt
uvicorn main:app --reload

4. Connect WhatsApp (Localhost)

To test locally, you need to expose your localhost to the internet.

    Run ngrok: ngrok http 8000

    Copy the URL (e.g., https://xyz.ngrok-free.app).

    Go to Meta Developers -> WhatsApp -> Configuration.

    Set Webhook URL to https://xyz.ngrok-free.app/webhook.

    Set Verify Token to match your .env file.

📂 Project Structure
Plaintext

├── app/
│   ├── agents/          # Pydantic AI Agent definitions
│   │   ├── core.py      # The main "HomeBase" agent
│   │   └── tools.py     # Database interaction tools (Log, Verify, etc.)
│   ├── database/
│   │   └── client.py    # PocketBase SDK wrappers
│   ├── routers/
│   │   └── whatsapp.py  # Webhook verification & message handling
│   └── utils/
│       └── scheduler.py # APScheduler logic for "Nagging"
├── main.py              # Application entry point
├── pocketbase_schema.json # DB Schema backup
└── README.md

☁️ Deployment (Railway)

We deploy this as two separate services within one Railway Project.

Service 1: PocketBase

    Use the PocketBase Template.

    CRITICAL: Attach a Volume mounted to /pb_data. If you skip this, you lose all data on restart.

Service 2: Python Worker

    Connect this GitHub repo.

    Set Environment Variables.

    Update POCKETBASE_URL to the Private Internal URL of Service 1 (e.g., http://pocketbase.railway.internal:8090).

🧪 Usage Examples

Defining a Chore:

    "Add a new chore called 'Scrub Toilet'. It needs to be done every Saturday. It's worth 3 points."

Logging Work:

    "I just finished scrubbing the toilet."

Checking Status:

    "Who is winning this month?" "Is there anything I need to do today?"

Resolving Conflict:

    "Vote PASS on the kitchen dispute."

Built for households that need a manager, not just a reminder.
