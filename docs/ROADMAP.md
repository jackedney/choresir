# choresir Development Roadmap

**Status:** Active Development
**Start Date:** 2026-01-15
**Approach:** Bottom-up with parallel tracks

This roadmap breaks down the ADRs into actionable development tasks organized into phases with clear dependencies.

---

## Phase 1: Foundation (Sequential)

These tasks must be completed in order before parallel tracks can begin.

### Task 1: Development Environment Setup
- Install and configure `uv`, `ruff`, `ty`
- Set up pyproject.toml with dependencies
- Configure ruff (120 char line length, import sorting)
- Configure ty for strict type checking
- **Dependencies:** None
- **Track:** Foundation

### Task 2: FastAPI Project Skeleton
- Create folder structure per ADR 006:
  ```
  src/
  ├── agents/         # Pydantic AI Agents, Tools, and Prompts
  ├── interface/      # FastAPI Routers (Webhooks, Admin) & WhatsApp Adapters
  ├── core/           # Config, Logging, Schema Management, DB Client
  ├── domain/         # Pydantic Data Models / DTOs
  ├── services/       # Functional Business Logic (Ledger, Bouncer, etc.)
  └── main.py         # App Entrypoint
  ```
- Create `main.py` with minimal FastAPI app
- Add health check endpoint
- **Dependencies:** Task 1
- **Track:** Foundation

### Task 3: PocketBase Setup
- Download PocketBase binary
- Start PocketBase locally (`./pocketbase serve`)
- Create admin account via `http://127.0.0.1:8090/_/`
- Document connection credentials
- **Dependencies:** None (can run parallel with Task 1-2)
- **Track:** Foundation

### Task 4: Core Config Module
- Create `src/core/config.py`
- Implement `.env` file handling
- Define environment variables:
  - `POCKETBASE_URL`
  - `OPENROUTER_API_KEY`
  - `WHATSAPP_VERIFY_TOKEN`
  - `WHATSAPP_APP_SECRET`
  - `LOGFIRE_TOKEN`
  - `HOUSE_CODE`
  - `HOUSE_PASSWORD`
  - `MODEL_ID` (defaults to Claude 3.5 Sonnet)
- Add constants (rate limits, timeout values)
- **Dependencies:** Task 2
- **Track:** Foundation

---

## Phase 2: Parallel Tracks

Once foundation is complete, these tracks can run simultaneously.

### Track A: Database Layer

#### Task 5: Pydantic Domain Models
- Create `src/domain/user.py`:
  - `User` model (id, phone, name, role, status)
  - Validation for E.164 phone format
- Create `src/domain/chore.py`:
  - `Chore` model (id, title, description, schedule_cron, assigned_to, current_state, deadline)
  - State enum (TODO, PENDING_VERIFICATION, COMPLETED, CONFLICT, DEADLOCK)
- Create `src/domain/log.py`:
  - `Log` model (id, chore_id, user_id, action, timestamp)
- **Dependencies:** Task 4
- **Track:** Database Layer

#### Task 6: PocketBase Schema Management
- Create `src/core/schema.py`
- Implement code-first schema sync script
- Define collections: `users`, `chores`, `logs`
- Run on application startup to ensure schema matches models
- **Dependencies:** Task 5
- **Track:** Database Layer

#### Task 7: PocketBase Client Wrapper
- Create `src/core/db_client.py`
- Implement connection pooling/handling
- Add CRUD helper methods
- Add error handling for network failures
- **Dependencies:** Task 6
- **Track:** Database Layer

### Track B: WhatsApp Interface

#### Task 8: Webhook Endpoint with Signature Verification
- Create `src/interface/webhook.py`
- Implement POST `/webhook` endpoint
- Validate `X-Hub-Signature-256` using `WHATSAPP_APP_SECRET`
- Return `200 OK` immediately (3-second timeout compliance)
- Add GET `/webhook` for verification handshake
- **Dependencies:** Task 4
- **Track:** WhatsApp Integration

#### Task 9: WhatsApp Message Parser
- Create `src/interface/whatsapp_parser.py`
- Extract text content from WhatsApp webhook payload
- Extract sender phone number (E.164 format)
- Extract message metadata (timestamp, message_id)
- Handle edge cases (no text, media-only messages)
- **Dependencies:** Task 8
- **Track:** WhatsApp Integration

#### Task 10: WhatsApp Response Formatter
- Create `src/interface/whatsapp_sender.py`
- Implement function to send text messages via WhatsApp Cloud API
- Handle rate limiting (in-memory for MVP)
- Add retry logic for failed sends
- **Dependencies:** Task 4
- **Track:** WhatsApp Integration

#### Task 11: WhatsApp Template Messages
- Register template messages in Meta Developer Console:
  - `chore_reminder`
  - `verification_request`
  - `conflict_notification`
- Implement 24-hour window detection logic
- Add template sender utility (fallback when >24h since last user message)
- **Dependencies:** Task 10
- **Track:** WhatsApp Integration

### Track C: Business Logic Services

#### Task 12: User Service (Onboarding)
- Create `src/services/user_service.py`
- Implement `request_join()`:
  - Validate house code + password against env vars
  - Create user with `status="pending"`
  - Return success/failure
- Implement `approve_member()`:
  - Admin-only check
  - Flip `status` to `active`
  - Send notification to approved user
- Implement `ban_user()` (admin-only)
- **Dependencies:** Task 7
- **Track:** Business Logic

#### Task 13: Chore Service (CRUD + State Machine)
- Create `src/services/chore_service.py`
- Implement `create_chore()`:
  - Parse recurrence string (CRON or "every X days")
  - Assign to user or mark "unassigned"
  - Set initial state to `TODO`
- Implement `get_chores()` (filters: user, state, time_range)
- Implement state transition functions:
  - `mark_pending_verification()`
  - `complete_chore()`
  - `move_to_conflict()`
- Implement floating schedule logic (calculate next deadline from completion time)
- **Dependencies:** Task 7
- **Track:** Business Logic

#### Task 14: Verification Service
- Create `src/services/verification_service.py`
- Implement `request_verification()`:
  - Transition chore to `PENDING_VERIFICATION`
  - Create log entry
  - Notify other household members
- Implement `verify_chore()`:
  - Accept user decision (APPROVE/REJECT)
  - If APPROVE: transition to `COMPLETED`, update deadline
  - If REJECT: transition to `CONFLICT`, trigger voting
- Add business rule: verifier cannot be the chore claimer
- **Dependencies:** Task 13
- **Track:** Business Logic

#### Task 15: Conflict Resolution Service (Voting)
- Create `src/services/conflict_service.py`
- Implement `initiate_vote()`:
  - Create vote records for all eligible members (exclude claimer + rejecter)
  - Send notifications with vote options
- Implement `cast_vote()`:
  - Record vote anonymously
  - Check if all votes are in
- Implement `tally_votes()`:
  - Odd population: majority wins
  - Even population: check for deadlock
  - Return result + transition chore state
- **Dependencies:** Task 14
- **Track:** Business Logic

#### Task 16: Analytics Service
- Create `src/services/analytics_service.py`
- Implement `get_leaderboard()`:
  - Count completed chores per user (default: 30 days)
  - Sort by completion count
- Implement `get_completion_rate()`:
  - Calculate % of chores completed on time vs overdue
- Implement `get_overdue_chores()`:
  - Filter chores where `deadline < now` and `state != COMPLETED`
- **Dependencies:** Task 7
- **Track:** Business Logic

### Track D: AI Agent

#### Task 17: Pydantic AI Agent Setup
- Create `src/agents/choresir_agent.py`
- Configure Pydantic AI agent with OpenRouter
- Implement system prompt template (from ADR 002):
  - Inject current user (name, phone)
  - Inject current timestamp
  - Add core directives (no fluff, strict neutrality, entity anchoring)
- **Dependencies:** Task 4
- **Track:** AI Agent

#### Task 18: Onboarding Agent Tools
- Create `src/agents/tools/onboarding_tools.py`
- Implement `tool_request_join`:
  - Schema: `RequestJoin(house_code, password, display_name)`
  - Call `user_service.request_join()`
- Implement `tool_approve_member`:
  - Schema: `ApproveMember(target_phone)`
  - Call `user_service.approve_member()`
- **Dependencies:** Task 12, Task 17
- **Track:** AI Agent

#### Task 19: Chore Management Agent Tools
- Create `src/agents/tools/chore_tools.py`
- Implement `tool_define_chore`:
  - Schema: `DefineChore(title, recurrence, assignee_phone)`
  - Call `chore_service.create_chore()`
- Implement `tool_log_chore`:
  - Schema: `LogChore(chore_title_fuzzy, notes, is_swap)`
  - Fuzzy match chore title
  - Call `verification_service.request_verification()`
- **Dependencies:** Task 13, Task 17
- **Track:** AI Agent

#### Task 20: Verification Agent Tools
- Create `src/agents/tools/verification_tools.py`
- Implement `tool_verify_chore`:
  - Schema: `VerifyChore(log_id, decision, reason)`
  - Call `verification_service.verify_chore()`
- Implement `tool_get_status`:
  - Schema: `GetStatus(target_user_phone, time_range)`
  - Call `chore_service.get_chores()` with filters
  - Format response for WhatsApp (concise)
- **Dependencies:** Task 14, Task 17
- **Track:** AI Agent

#### Task 21: Analytics Agent Tools
- Create `src/agents/tools/analytics_tools.py`
- Implement `tool_get_analytics`:
  - Schema: `GetAnalytics(metric, period_days)`
  - Call `analytics_service.get_leaderboard()` or `get_completion_rate()`
  - Format response (e.g., "Top 3: Alice (12), Bob (8), Charlie (5)")
- **Dependencies:** Task 16, Task 17
- **Track:** AI Agent

#### Task 22: Context Injection
- Update `choresir_agent.py`
- Implement context injection before agent execution:
  - Look up user from phone number
  - Get user role (admin/member)
  - Get current timestamp
  - Inject into system prompt
- Add error handling for unknown users
- **Dependencies:** Task 17
- **Track:** AI Agent

---

## Phase 3: Integration (Sequential)

These tasks wire everything together. Must complete after Tracks B + D.

### Task 23: Webhook → BackgroundTasks Integration
- Update `src/interface/webhook.py`
- Dispatch agent execution to `FastAPI.BackgroundTasks`
- Pass parsed message + user context to agent
- Send agent response back via WhatsApp
- Add error handling (catch exceptions, send error message to user)
- **Dependencies:** Task 9, Task 22
- **Track:** Integration

### Task 24: APScheduler for Reminders
- Create `src/core/scheduler.py`
- Set up APScheduler in FastAPI app
- Schedule daily job (e.g., 8am):
  - Check for overdue chores
  - Send reminders to assigned users
- Schedule daily report (e.g., 9pm):
  - Summary of today's completions
  - Send to all active users
- **Dependencies:** Task 13, Task 10
- **Track:** Integration

### Task 25: Pydantic Logfire Instrumentation
- Create `src/core/logging.py`
- Configure Pydantic Logfire with `LOGFIRE_TOKEN`
- Add FastAPI middleware for request tracing
- Add Pydantic AI tracing (automatic for agent calls)
- Add custom spans for service layer functions
- **Dependencies:** Task 4, Task 23
- **Track:** Integration

---

## Phase 4: Quality & Deployment

These can be done in parallel.

### Testing Track

#### Task 26: Integration Test Harness
- Create `tests/conftest.py`
- Implement ephemeral PocketBase fixture:
  - Spin up temporary `pb_data` directory
  - Start PocketBase process
  - Yield connection URL
  - Teardown on test completion
- Add test fixtures for sample data (users, chores)
- **Dependencies:** Task 7
- **Track:** Testing

#### Task 27: Core Workflow Integration Tests
- Create `tests/test_workflows.py`
- Test "Join House" workflow (request → approve → active)
- Test "Create & Complete Chore" workflow (create → log → verify → completed)
- Test "Conflict Resolution" workflow (log → reject → vote → resolve)
- Test "Robin Hood Swap" workflow (User A logs User B's chore)
- **Dependencies:** Task 26, Task 23
- **Track:** Testing

### DevOps Track

#### Task 28: Railway PocketBase Service
- Create `railway.toml` for PocketBase service
- Configure persistent volume mount to `/pb_data`
- Set health check endpoint
- Document environment variables
- **Dependencies:** None
- **Track:** DevOps

#### Task 29: Railway Python Worker
- Create `railway.toml` for FastAPI worker
- Connect to GitHub repo
- Set `POCKETBASE_URL` to internal service URL
- Add build command: `uv sync`
- Add start command: `uv run fastapi run src/main.py --port $PORT`
- **Dependencies:** Task 28
- **Track:** DevOps

#### Task 30: Local Webhook Testing Setup
- Document ngrok setup process
- Create script to start ngrok: `ngrok http 8000`
- Document how to update Meta Developer Console webhook URL
- Add troubleshooting guide for common issues
- **Dependencies:** Task 8
- **Track:** DevOps

---

## Execution Strategy for Conductor

### Session 1: Foundation (Sequential)
```
Agent 1: Tasks 1-4
```
**Output:** Project skeleton ready, PocketBase running, environment configured

### Session 2: Parallel Tracks
```
Agent 1 (Database): Tasks 5-7
Agent 2 (WhatsApp): Tasks 8-11
Agent 3 (Services): Tasks 12-16 (starts after Task 7 completes)
Agent 4 (AI Agent): Tasks 17-22 (starts after Task 7 completes)
```
**Output:** All core components implemented

### Session 3: Integration
```
Agent 1: Tasks 23-25
```
**Output:** End-to-end system functional

### Session 4: Quality & Deployment
```
Agent 1 (Testing): Tasks 26-27
Agent 2 (DevOps): Tasks 28-30
```
**Output:** Production-ready system

---

## Task Dependencies Visualization

```
Foundation Phase:
Task 1 → Task 2 → Task 4
Task 3 (parallel)

Parallel Tracks:
Task 4 → Task 5 → Task 6 → Task 7
                            ↓
Task 4 → Task 8 → Task 9        Task 12 → Task 13 → Task 14 → Task 15
         ↓
Task 4 → Task 10 → Task 11       Task 16
                                 ↓
                  Task 4 → Task 17 → Task 18, 19, 20, 21 → Task 22

Integration Phase:
Task 9 + Task 22 → Task 23
Task 13 + Task 10 → Task 24
Task 4 + Task 23 → Task 25

Quality Phase:
Task 7 → Task 26 → Task 27
Task 8 → Task 30
(Task 28, 29 independent)
```

---

## Progress Tracking

- [x] Phase 1: Foundation (4/4 tasks) ✅ **COMPLETE**
- [x] Phase 2: Parallel Tracks (18/18 tasks) ✅ **COMPLETE**
  - [x] Track A: Database (3/3 tasks) ✅ **COMPLETE**
  - [x] Track B: WhatsApp (4/4 tasks) ✅ **COMPLETE**
  - [x] Track C: Services (5/5 tasks) ✅ **COMPLETE**
  - [x] Track D: AI Agent (6/6 tasks) ✅ **COMPLETE**
- [x] Phase 3: Integration (3/3 tasks) ✅ **COMPLETE**
  - [x] Task 23: Webhook → BackgroundTasks Integration ✅ **COMPLETE**
  - [x] Task 24: APScheduler for Reminders ✅ **COMPLETE**
  - [x] Task 25: Pydantic Logfire Instrumentation ✅ **COMPLETE**
- [ ] Phase 4: Quality & Deployment (3/5 tasks)
  - [ ] Testing Track (0/2 tasks)
  - [x] DevOps Track (3/3 tasks) ✅ **COMPLETE**

**Total Progress: 28/30 tasks (93.3%)**

---

## Notes

- **Granularity:** Each task is a complete, testable unit representing a logical module or feature
- **Parallelization:** Tracks B, C, D can run simultaneously after Track A completes Task 7
- **Testing Strategy:** Per ADR 007, we use integration tests with ephemeral PocketBase instances
- **Code Standards:** All code must follow ADR 006 (ruff, ty, functional style, guard clauses)

---

## Next Steps

1. Begin with Foundation Phase (Tasks 1-4)
2. Once complete, launch parallel agents for Tracks A-D
3. Monitor for blockers or dependencies
4. Iterate on this roadmap as needed

**Last Updated:** 2026-01-16
