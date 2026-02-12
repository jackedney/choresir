# Modularization Plan: WhatsApp Home Boss

## Context

The project is a FastAPI + Pydantic AI + SQLite WhatsApp bot currently hardcoded for household chore management. It has significant code duplication between "chores" and "personal chores" (~800 lines), a 110-line chore-specific system prompt, 14+ service files with overlapping concerns, and hardcoded scheduler jobs. The goal is to reduce bloat, introduce a formal module/plugin architecture, unify the task model, simplify the lifecycle (remove conflict/voting), and make the bot configurable for different use cases.

**User decisions:**
- Full plugin system with Module Protocol
- Keep pantry + Robin Hood as optional modules
- Remove conflict resolution (no voting, rejection → back to TODO)
- Configurable bot name/personality via env vars

---

## Phase 0: Preparatory Deduplication (no architecture change)

### 0.1 Extract shared fuzzy matching

**Create:** `src/core/fuzzy_match.py`

Extract the duplicated fuzzy match logic from these 3 locations into one parameterized utility:
- `src/agents/tools/chore_tools.py` (lines 87-139) - `_fuzzy_match_chore`, `_fuzzy_match_all_chores`
- `src/agents/tools/verification_tools.py` (lines 18-70) - same functions
- `src/services/personal_chore_service.py` (lines 156-193) - `fuzzy_match_personal_chore`

New function signature: `fuzzy_match(items, title_query, *, title_key="title") -> dict | None`

Update all 3 source files to import from `src.core.fuzzy_match`.

**~100 lines eliminated.**

### 0.2 Extract notification message templates

**Create:** `src/core/message_templates.py`

Extract inline f-string message templates from `src/services/notification_service.py` and `src/core/scheduler.py` into named template functions. This centralizes domain vocabulary for easier future customization.

---

## Phase 1: Unified Task Model

### 1.1 New schema - replace 4 tables with 2

**Modify:** `src/core/schema.py`

**Remove tables:** `chores`, `personal_chores`, `logs`, `personal_chore_logs`

**Add table `tasks`:**
```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL DEFAULT (datetime('now')),
    updated TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL,
    description TEXT,
    schedule_cron TEXT,
    deadline TEXT,
    owner_id INTEGER REFERENCES members(id),
    assigned_to INTEGER REFERENCES members(id),
    scope TEXT NOT NULL CHECK (scope IN ('shared', 'personal')),
    verification TEXT NOT NULL DEFAULT 'none'
        CHECK (verification IN ('none', 'peer', 'partner')),
    accountability_partner_id INTEGER REFERENCES members(id),
    current_state TEXT NOT NULL DEFAULT 'TODO'
        CHECK (current_state IN ('TODO', 'PENDING_VERIFICATION', 'COMPLETED', 'ARCHIVED')),
    module TEXT NOT NULL DEFAULT 'task'
)
```

**Add table `task_logs`:**
```sql
CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL DEFAULT (datetime('now')),
    updated TEXT NOT NULL DEFAULT (datetime('now')),
    task_id INTEGER REFERENCES tasks(id),
    user_id INTEGER REFERENCES members(id),
    action TEXT NOT NULL,
    notes TEXT,
    timestamp TEXT,
    verification_status TEXT CHECK (
        verification_status IN ('SELF_VERIFIED', 'PENDING', 'VERIFIED', 'REJECTED')
    ),
    verifier_id INTEGER REFERENCES members(id),
    verifier_feedback TEXT,
    original_assignee_id INTEGER REFERENCES members(id),
    actual_completer_id INTEGER REFERENCES members(id),
    is_swap INTEGER DEFAULT 0
)
```

Key design: `scope` differentiates shared vs personal. `verification` controls lifecycle complexity. `module` tag allows future modules to register their own task types.

**Simplified lifecycle (no conflict/voting):**
- `TODO → COMPLETED` (verification=none)
- `TODO → PENDING_VERIFICATION → COMPLETED` (approved)
- `TODO → PENDING_VERIFICATION → TODO` (rejected, back to start)
- Any → `ARCHIVED`

**Remove states:** `CONFLICT`, `DEADLOCK`

### 1.2 Update domain models

**Delete:** `src/domain/chore.py`
**Create:** `src/domain/task.py`

```python
class TaskScope(StrEnum): SHARED, PERSONAL
class VerificationType(StrEnum): NONE, PEER, PARTNER
class TaskState(StrEnum): TODO, PENDING_VERIFICATION, COMPLETED, ARCHIVED
class Task(BaseModel): ...  # mirrors the tasks table
```

**Update:** `src/domain/log.py` - rename to reference task_logs, add verification fields

### 1.3 Update workflow_service

**Modify:** `src/services/workflow_service.py`
- Change `WorkflowType` enum: replace `chore_verification` + `personal_verification` with `task_verification`
- Update CHECK constraint in schema for workflows table

### 1.4 Migration script

**Create:** `scripts/migrate_v1_to_v2.py`
- Copy `chores` → `tasks` with `scope='shared'`, `verification='peer'`
- Copy `personal_chores` → `tasks` with `scope='personal'`, map partner phone→id
- Copy `logs` → `task_logs`, map chore_id→task_id
- Copy `personal_chore_logs` → `task_logs`, map fields
- Update workflow type values in `workflows` table
- Drop old tables after verification
- Add `schema_version` to `house_config`

---

## Phase 2: Module/Plugin Architecture

### 2.1 Define Module protocol

**Create:** `src/core/module.py`

```python
class Module(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    def get_table_schemas(self) -> dict[str, str]: ...
    def get_indexes(self) -> list[str]: ...
    def register_tools(self, agent: Agent[Deps, str]) -> None: ...
    def get_system_prompt_section(self) -> str: ...
    def get_scheduled_jobs(self) -> list[dict[str, Any]]: ...
    def get_config_fields(self) -> dict[str, Any]: ...
```

### 2.2 Module registry

**Create:** `src/core/module_registry.py`

Functions: `register_module()`, `get_modules()`, `get_module()`, `get_all_table_schemas()`, `get_all_indexes()`

### 2.3 Create module packages

**Create directory:** `src/modules/`

```
src/modules/
    __init__.py
    tasks/
        __init__.py          # TasksModule class
        tools.py             # Merged from chore_tools + personal_chore_tools + verification_tools + analytics_tools
        service.py           # Merged from chore_service + personal_chore_service
        verification.py      # Merged from verification_service + personal_verification_service
        state_machine.py     # Simplified (no conflict states)
        deletion.py          # From deletion_service
        analytics.py         # From analytics_service
        robin_hood.py        # From robin_hood_service
        scheduler_jobs.py    # Overdue reminders, daily report, weekly leaderboard, personal reminders
        prompt.py            # Task-related system prompt section
    pantry/
        __init__.py          # PantryModule class
        tools.py             # From pantry_tools
        service.py           # Pantry service logic (inline or from existing)
        prompt.py            # Pantry system prompt section
    onboarding/
        __init__.py          # OnboardingModule class
        tools.py             # From onboarding_tools
        prompt.py            # Onboarding system prompt section
```

### 2.4 Make schema.py module-aware

**Modify:** `src/core/schema.py`

Split `TABLE_SCHEMAS` into `CORE_TABLE_SCHEMAS` (members, processed_messages, house_config, bot_messages, group_context, join_sessions, workflows) and module-contributed schemas via registry.

`init_db()` creates core tables first, then iterates `module_registry.get_all_table_schemas()`.

### 2.5 Make scheduler module-aware

**Modify:** `src/core/scheduler.py`

Replace the hardcoded 8-job `start_scheduler()` with:
- Core jobs: `expire_workflows`, `cleanup_group_context`
- Module jobs: iterate `module.get_scheduled_jobs()` for each registered module

### 2.6 Make health check dynamic

**Modify:** `src/main.py`

Replace hardcoded `job_names` list (lines 101-110) with dynamic list from registered modules + core jobs.

### 2.7 Wire up in main.py

**Modify:** `src/main.py`

In `lifespan()`:
```python
register_module(TasksModule())
register_module(PantryModule())
register_module(OnboardingModule())
await init_db()  # Now module-aware
start_scheduler()  # Now module-aware
```

---

## Phase 3: Configurable Agent

### 3.1 Add bot config env vars

**Modify:** `src/core/config.py`

```python
bot_name: str = Field(default="choresir")
bot_description: str = Field(default="household management assistant")
```

### 3.2 Composable system prompt

**Modify:** `src/agents/choresir_agent.py`

Replace the 110-line `SYSTEM_PROMPT_TEMPLATE` with a composed prompt:
1. **Base section** (always present, domain-agnostic): core directives, current context, member list. Uses `settings.bot_name` and `settings.bot_description`.
2. **Module sections**: iterate registered modules calling `module.get_system_prompt_section()`
3. **Dynamic context**: pending workflows, conversation/group history (unchanged)

Each module's `prompt.py` provides its section. For example, `src/modules/tasks/prompt.py` contains the task management instructions, and `src/modules/pantry/prompt.py` contains pantry instructions.

### 3.3 Module-driven tool registration

**Modify:** `src/agents/agent_instance.py`

Replace `_register_all_tools()` hardcoded imports with:
```python
for module in get_modules().values():
    module.register_tools(agent_instance)
```

---

## Phase 4: Service Consolidation & Cleanup

### 4.1 Services relocated to modules

| Current File | Destination | Action |
|---|---|---|
| `chore_service.py` | `src/modules/tasks/service.py` | Merge into unified task_service |
| `personal_chore_service.py` | `src/modules/tasks/service.py` | Merge (eliminated) |
| `chore_state_machine.py` | `src/modules/tasks/state_machine.py` | Simplify (remove CONFLICT/DEADLOCK) |
| `verification_service.py` | `src/modules/tasks/verification.py` | Merge with personal |
| `personal_verification_service.py` | `src/modules/tasks/verification.py` | Merge (eliminated) |
| `conflict_service.py` | **DELETE** | Removed per user decision |
| `robin_hood_service.py` | `src/modules/tasks/robin_hood.py` | Relocate |
| `deletion_service.py` | `src/modules/tasks/deletion.py` | Relocate |
| `analytics_service.py` | `src/modules/tasks/analytics.py` | Relocate |

### 4.2 Services kept in `src/services/` (generic/core)

| Service | Reason |
|---|---|
| `user_service.py` | Generic user management |
| `workflow_service.py` | Generic approval state machine |
| `notification_service.py` | Generic WhatsApp dispatch (generalize messages) |
| `conversation_context_service.py` | Generic conversation history |
| `group_context_service.py` | Generic group context |
| `house_config_service.py` | Generic config |
| `activation_key_service.py` | Generic activation flow |
| `lid_resolver.py` | WhatsApp LID resolution |

### 4.3 Tool file cleanup

| Current File | Destination | Action |
|---|---|---|
| `agents/tools/chore_tools.py` | `modules/tasks/tools.py` | Merge |
| `agents/tools/personal_chore_tools.py` | `modules/tasks/tools.py` | Merge (eliminated) |
| `agents/tools/verification_tools.py` | `modules/tasks/tools.py` | Merge |
| `agents/tools/analytics_tools.py` | `modules/tasks/tools.py` | Merge |
| `agents/tools/pantry_tools.py` | `modules/pantry/tools.py` | Relocate |
| `agents/tools/onboarding_tools.py` | `modules/onboarding/tools.py` | Relocate |

After: `src/agents/tools/` directory is **deleted** (empty).

### 4.4 Update domain model files

- **Delete:** `src/domain/chore.py`, `src/domain/create_models.py`, `src/domain/update_models.py`
- **Create:** `src/domain/task.py` (unified model)
- **Keep:** `src/domain/user.py`, `src/domain/pantry.py`, `src/domain/log.py` (updated)

---

## Phase 5: Interface Updates

### 5.1 Webhook updates

**Modify:** `src/interface/webhook.py`
- Change `collection="logs"` references to `collection="task_logs"`
- Change `collection="chores"` references to `collection="tasks"`
- Button handler: update payload processing for `task_logs` table

### 5.2 Admin dashboard updates

**Modify:** `src/interface/admin_router.py` and templates
- Update any chore-specific references in dashboard stats
- Use `settings.bot_name` for display name in templates

### 5.3 Update main.py metadata

**Modify:** `src/main.py`
- Replace hardcoded `title="choresir"` with `settings.bot_name`
- Replace hardcoded `description` with `settings.bot_description`

---

## Phase 6: Test Updates

Update test imports and assertions across all test files:
- `test_chore_service.py` → test against `task_service`
- `test_chore_tools.py` → test against merged tools
- `test_verification_service.py` + `test_personal_verification_service.py` → merge
- `test_conflict_service.py` → **delete**
- Update all `collection="chores"` references to `collection="tasks"`

---

## Files Summary

### Created (~15 files)
- `src/core/fuzzy_match.py`
- `src/core/message_templates.py`
- `src/core/module.py`
- `src/core/module_registry.py`
- `src/domain/task.py`
- `src/modules/__init__.py`
- `src/modules/tasks/__init__.py`, `tools.py`, `service.py`, `verification.py`, `state_machine.py`, `deletion.py`, `analytics.py`, `robin_hood.py`, `scheduler_jobs.py`, `prompt.py`
- `src/modules/pantry/__init__.py`, `tools.py`, `service.py`, `prompt.py`
- `src/modules/onboarding/__init__.py`, `tools.py`, `prompt.py`
- `scripts/migrate_v1_to_v2.py`

### Deleted (~14 files)
- `src/domain/chore.py`
- `src/services/chore_service.py`
- `src/services/personal_chore_service.py`
- `src/services/chore_state_machine.py`
- `src/services/verification_service.py`
- `src/services/personal_verification_service.py`
- `src/services/conflict_service.py`
- `src/services/robin_hood_service.py`
- `src/services/deletion_service.py`
- `src/services/analytics_service.py`
- `src/agents/tools/chore_tools.py`
- `src/agents/tools/personal_chore_tools.py`
- `src/agents/tools/verification_tools.py`
- `src/agents/tools/analytics_tools.py`
- `src/agents/tools/pantry_tools.py`
- `src/agents/tools/onboarding_tools.py`

### Modified (~10 files)
- `src/core/schema.py` - Core vs module table split
- `src/core/config.py` - Add bot_name, bot_description
- `src/core/scheduler.py` - Module-aware job registration
- `src/agents/choresir_agent.py` - Composable system prompt
- `src/agents/agent_instance.py` - Module-driven tool registration
- `src/services/workflow_service.py` - Unified workflow type
- `src/services/notification_service.py` - Generalized messages
- `src/interface/webhook.py` - Table reference updates
- `src/interface/admin_router.py` - Bot name in templates
- `src/main.py` - Module registration, dynamic health check

### Unchanged (infrastructure layer)
- `src/core/db_client.py`, `rate_limiter.py`, `errors.py`, `admin_notifier.py`, `logging.py`, `cache_client.py`, `recurrence_parser.py`, `scheduler_tracker.py`
- `src/interface/webhook_security.py`, `whatsapp_parser.py`, `whatsapp_sender.py`
- `src/services/user_service.py`, `conversation_context_service.py`, `group_context_service.py`, `house_config_service.py`, `activation_key_service.py`, `lid_resolver.py`
- `src/agents/base.py`, `retry_handler.py`
- `src/domain/user.py`, `pantry.py`

---

## Estimated Impact

- **~800-1000 lines eliminated** from deduplication (chore + personal chore merge)
- **~200 lines eliminated** from conflict resolution removal
- **~100 lines eliminated** from fuzzy match deduplication
- **~200 lines added** for module infrastructure (Protocol, registry, `__init__` files)
- **Net reduction: ~800-1100 lines** with better organization

---

## Implementation Order & Dependencies

```
Phase 0 ──── No dependencies, safe deduplication
   ↓
Phase 1 ──── Schema + service unification (biggest risk, do carefully)
   ↓
Phase 2 ──── Module architecture (depends on Phase 1 for module contents)
   ↓
Phase 3 ──── Configurable agent (depends on Phase 2 for module registry)
   ↓
Phase 4 ──── Cleanup (depends on Phases 1-3, relocate files)
   ↓
Phase 5 ──── Interface updates (depends on Phase 1 for table names)
   ↓
Phase 6 ──── Test updates (last, depends on everything)
```

---

## Verification

After each phase:
1. Run `task test` (pytest) - all existing tests must pass (with import updates)
2. Run `task lint` (ruff) - no lint errors
3. Manual test: send a WhatsApp message, verify bot responds correctly
4. Check admin UI at `/admin/` - dashboard, members, WhatsApp setup all functional

After all phases:
1. Run the migration script on a DB copy, verify data integrity
2. Start fresh with empty DB, create tasks via WhatsApp, verify full lifecycle
3. Test scheduled jobs fire correctly via `/health/scheduler`
4. Verify pantry module works independently of tasks
5. Change `BOT_NAME` env var, verify system prompt updates

---

## Risk Areas

1. **Schema migration** - Most dangerous step. Test on DB copy first. Keep old tables as backup during transition.
2. **Circular imports** - Modules must not import from each other. They communicate through `src/services/` or via module registry. Use lazy imports in `register_tools()`.
3. **In-flight WhatsApp messages** - Button payloads reference `logs` table. Need transition handling or flush pending verifications before migrating.
4. **Test breakage** - 30+ test files will need import path updates. Update alongside each phase, not as a big bang.
