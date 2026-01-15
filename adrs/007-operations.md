# ADR 007: Operational Strategy & Data Schema

## Status
Accepted

## Date
2026-01-14

## Context
We need to define the "invisible" operational mechanics of the bot: how it handles files, how users get in, and how data is structured.

**Deployment Model:** Single Tenancy. One instance of this application serves exactly one household.

## Decisions

### 1. Onboarding Protocol (The "Bouncer")
We rejected a public "Wild West" open join. We also rejected a purely manual Admin-only add.
We will implement a **Two-Stage Approval Flow**:

1.  **Request:** A user messages the bot with a House Code + Password (e.g., "Join HOUSE123 SecretPass").
2.  **Pending:** The bot validates the credentials against environment variables. If correct, the user is created in `users` with `status="pending"`.
3.  **Approval:** The bot notifies existing Admin users. An Admin must reply "Approve [Name]" to flip `status` to `active`.

### 2. Data Schema (The Blueprint)
The PocketBase schema will adhere to this structure:

#### `users`
*   `id`: Record ID
*   `phone`: String (Unique, E.164 format)
*   `name`: String (Display name)
*   `role`: Select (`admin`, `member`)
*   `status`: Select (`pending`, `active`, `banned`)

#### `chores`
*   `id`: Record ID
*   `title`: String (e.g., "Wash Dishes")
*   `description`: Text
*   `schedule_cron`: String (e.g., `0 20 * * *`) or Interval (e.g., "3 days")
*   `assigned_to`: Relation (-> `users`) **[Single]**
    *   *Note:* To assign a chore to multiple people (e.g., "Alice and Bob"), create multiple `Chore` records (one per person).
*   `current_state`: Select (`TODO`, `PENDING_VERIFICATION`, `COMPLETED`, `CONFLICT`, `DEADLOCK`)
*   `deadline`: DateTime
    *   *Recurrence Note:* Floating Schedule. The next deadline is calculated from the **Completion Time** of the previous instance, not the original due date.

#### `logs` (Audit Trail)
*   `id`: Record ID
*   `chore_id`: Relation (-> `chores`)
*   `user_id`: Relation (-> `users`) (The actor)
*   `action`: String (`completed`, `verified`, `rejected`, `voted_yes`)
*   `timestamp`: DateTime (Auto)

### 3. WhatsApp Integration Strategy (The 24h Wall)
Meta enforces a 24-hour window for free-form responses.
*   **Decision:** We will register **Template Messages** (e.g., `chore_reminder`, `verification_request`) to break the 24h barrier.
*   **Implementation:** The `Notifier` service will check the time since the last user message. If >24h, it sends a Template; otherwise, it sends free text.

### 4. Testing Strategy (The "Real" Test)
We reject "mocking the world."
*   **Decision:** Integration tests will spin up an **ephemeral PocketBase instance** (using a temporary `pb_data` directory).
*   **Reasoning:** This ensures our SQL queries and Pydantic AI tool calls work against the actual database engine, not just a mock that "always says yes."

## Consequences
*   **Security:** The House Code prevents random spam. The Admin Approval prevents "friend of a friend" leaks.
*   **Performance:** Streaming media keeps memory footprint low (assuming images < 10MB).
