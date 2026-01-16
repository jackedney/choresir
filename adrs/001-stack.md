ADR 001: Adoption of "Indie Stack" (Python + PocketBase)

Status: Accepted Date: 2026-01-14 Deciders: Product Owner, Project Manager Technical Context: The project requires a backend to handle WhatsApp Webhooks, store relational data (users, chores, logs), and manage complex business logic (voting, swapping). The team consists of a single developer proficient in Python. The scale is small (1–8 concurrent users), prioritizing low maintenance and zero cost over infinite horizontal scalability.

Decision: We will use Python (FastAPI) for the application logic and PocketBase (SQLite) for the database.

    FastAPI allows us to use native Python for the AI agent logic.
    
    We will use **APScheduler** (Advanced Python Scheduler) running within the FastAPI process to handle time-based triggers for **daily reporting and reminders**.
    *   *Note:* Core chore deadlines use a "Floating Schedule" (calculated from completion time) and are not driven directly by Cron, though the Scheduler triggers the check.

    PocketBase provides a portable, single-file database with a built-in Admin UI, removing the need to manage a separate PostgreSQL instance or complex ORMs.

    Hosting: Both services will be deployed on Railway (Service-to-Service networking).

    **Observability:** We will use **Pydantic Logfire**.
    *   It integrates natively with Pydantic AI and FastAPI.
    *   It provides structured tracing for LLM calls without custom instrumentation.

## Technical Implementation Details (Refined 2026-01-15)

*   **Concurrency:** To satisfy WhatsApp's 3-second timeout, the webhook endpoint will return `200 OK` immediately and dispatch the Pydantic AI agent execution to `FastAPI.BackgroundTasks`.
*   **Schema Management:** We adopt a **Code-First** approach. A `src/core/schema.py` script will run on application startup to ensure the PocketBase schema matches our Pydantic models.
*   **Security:** We will enforce `X-Hub-Signature-256` validation using the `WHATSAPP_APP_SECRET`.
*   **DevOps:**
    *   Local development uses `ngrok` for webhook tunneling.
    *   Secrets managed via `.env`.
    *   Rate limiting and Cost Caps ($0.10/day) implemented in-memory for the MVP.

## WhatsApp Provider: Twilio (Revised 2026-01-16)

**Decision:** We will use **Twilio WhatsApp API** instead of Meta's direct Cloud API.

**Rationale:**
*   Twilio provides a simpler abstraction over Meta's WhatsApp Business Platform
*   Unified API pattern (same SDK for SMS, WhatsApp, Voice)
*   Simpler webhook signature validation using Twilio's `RequestValidator`
*   No Meta Developer Console complexity (app review, business verification)
*   Built-in sandbox for testing without production approval
*   Better documentation and Python SDK support

**Trade-offs:**
*   Slightly higher per-message cost (Twilio markup)
*   Additional vendor dependency
*   Template messages require Twilio Content API setup

### Twilio Infrastructure Provisioning (Decided 2026-01-16)

**Decision:** We will use **manual setup via Twilio Console** rather than Infrastructure as Code (IaC) tools like Pulumi or Terraform.

**Rationale:**
*   **Language Mismatch:** Available Pulumi Twilio providers are TypeScript/Node.js only, requiring npm/JavaScript in an otherwise Python-only project
*   **Limited Scope:** Only 2 of 12 migration tasks (template creation, webhook configuration) could be automated via IaC
*   **One-Time Setup:** Twilio configuration is essentially static after initial provisioning, not frequently-changing infrastructure
*   **Experimental Status:** Community Pulumi providers are not production-ready
*   **Complexity vs. Value:** Adding IaC tooling contradicts the "Indie Stack" philosophy of low maintenance and minimal dependencies
*   **Manual Simplicity:** Current step-by-step guides can be executed in ~30 minutes with clear completion criteria

**Alternative Considered:**
Writing a Python script using Twilio SDK directly for programmatic setup was considered but rejected as unnecessary given the one-time nature of configuration and the need for WhatsApp approval (24-48 hours) regardless of automation method.

**Implementation:**
*   Account setup, sandbox configuration, and template creation documented in `.context/` task files
*   Templates require manual WhatsApp approval via Twilio Console
*   Webhook configuration tied to deployment environment (ngrok for local, Railway URL for production)

Consequences:

    Positive: rapid development; "zero-config" database; extremely portable (can move to a $5 VPS easily).

    Negative: PocketBase is vertically scaled (single instance). If the app suddenly hits 10,000 users, we would need to migrate to PostgreSQL.

    Risk: PocketBase relies on the local filesystem. We must ensure persistent storage (Volumes) is configured correctly on Railway, or data will be lost on restart.
