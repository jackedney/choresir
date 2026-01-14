ADR 001: Adoption of "Indie Stack" (Python + PocketBase)

Status: Accepted Date: 2026-01-14 Deciders: Product Owner, Project Manager Technical Context: The project requires a backend to handle WhatsApp Webhooks, store relational data (users, chores, logs), and manage complex business logic (voting, swapping). The team consists of a single developer proficient in Python. The scale is small (1–8 concurrent users), prioritizing low maintenance and zero cost over infinite horizontal scalability.

Decision: We will use Python (FastAPI) for the application logic and PocketBase (SQLite) for the database.

    FastAPI allows us to use native Python for the AI agent logic.
    
    We will use **APScheduler** (Advanced Python Scheduler) running within the FastAPI process to handle time-based triggers (cron jobs) for chore reminders and recurring tasks, keeping the deployment self-contained.

    PocketBase provides a portable, single-file database with a built-in Admin UI, removing the need to manage a separate PostgreSQL instance or complex ORMs.

    Hosting: Both services will be deployed on Railway (Service-to-Service networking).

    **Observability:** We will use **Pydantic Logfire**.
    *   It integrates natively with Pydantic AI and FastAPI.
    *   It provides structured tracing for LLM calls without custom instrumentation.

Consequences:

    Positive: rapid development; "zero-config" database; extremely portable (can move to a $5 VPS easily).

    Negative: PocketBase is vertically scaled (single instance). If the app suddenly hits 10,000 users, we would need to migrate to PostgreSQL.

    Risk: PocketBase relies on the local filesystem. We must ensure persistent storage (Volumes) is configured correctly on Railway, or data will be lost on restart.
