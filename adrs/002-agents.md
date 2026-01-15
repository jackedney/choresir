# ADR 002: Use of Pydantic AI for Agentic Logic

## Status
Accepted

## Date
2026-01-14

## Context
The application requires an LLM to interpret natural language, extract structured entities (Chore, Time, Assignee), and execute database tools. The landscape includes LangChain, AutoGen, and n8n. The primary constraint is maintainability for a single developer.

## Decision
We will use **Pydantic AI**.

1.  We rejected **LangChain** due to its high abstraction complexity and frequent breaking changes.
2.  We rejected **n8n** because the complex business logic (voting/swapping) is harder to version control and debug in a visual flowchart.
3.  **Pydantic AI** integrates natively with FastAPI (both use Pydantic models), allowing us to share data validation schemas between the HTTP API and the AI Agent.

## Consequences

### Positive
*   Type safety.
*   Pure Python code (easier to debug).
*   Lightweight dependency.

### Negative
*   Smaller ecosystem/community support compared to LangChain.

### Mitigation
We will rely on raw OpenAI-compatible API calls if Pydantic AI lacks a specific specific integration we need.

---

# Agent Specification: choresir

**Framework:** Pydantic AI | **Model:** Claude 3.5 Sonnet

## 1. Architecture Overview
choresir utilizes a **Single-Agent, Multi-Tool Architecture**. Instead of chaining multiple specialized agents (which increases latency and complexity), we use a single, high-intelligence `chore_sir_Core` agent equipped with context-aware tools.

*   **Input:** Raw natural language from WhatsApp + User Context (Name, Role).
*   **Context:** The agent is injected with the current user's profile and the current time.
*   **Output:** Natural language response + Tool Calls (Database Mutations).

## 2. System Persona
The agent is a **neutral, efficient Household Manager**. It should feel slightly authoritative but fair—like a professional third-party administrator.

**Core Directives:**
*   **No fluff:** Keep WhatsApp responses concise (under 2 sentences unless summarizing data).
*   **Strict Neutrality:** In conflicts, state the rules, do not take sides.
*   **Entity Anchoring:** Always map vague terms ("The kitchen thing") to specific database IDs before acting.
*   **Media Handling:** Ignore all images, audio, and video files. Text only.
*   **Proactivity:** You are authorized to send unsolicited messages if a chore is significantly overdue or unassigned for > 3 days.

**System Prompt Template:**
```text
You are choresir, the household operations manager.
Current User: {user_name} ({user_phone})
Current Time: {current_timestamp}

Your goal is to maintain the household database. You do not do chores; you log them, assign them, and verify them.
- If a stranger says "Join", use `request_join`.
- If a user claims a task, you MUST use the `log_chore` tool.
- If a user asks about status, use the `get_analytics` or `check_chore_status` tools.

Tone: Professional, brief, and objective.
```

## 3. Tool Capabilities (The "Hands")

### A. Core Operations (The Ledger)
These tools modify the state of the household.

#### `tool_define_chore`
*   **Trigger:** "Remind us to mow the lawn every 2 weeks."
*   **Schema:**
    ```python
    class DefineChore(BaseModel):
        title: str            # e.g., "Mow Lawn"
        recurrence: str       # e.g., "every 14 days" or CRON
        assignee_phone: str | None  # None if "up for grabs"
        # Note: No points. 1 chore = 1 unit of work.
    ```

#### `tool_log_chore`
*   **Trigger:** "I did the dishes." (Text only - no images required)
*   **Schema:**
    ```python
    class LogChore(BaseModel):
        chore_title_fuzzy: str # e.g., "dishes" (System will fuzzy match)
        notes: str | None
        is_swap: bool          # True if claiming someone else's task
    ```

#### `tool_verify_chore`
*   **Trigger:** "Yes, Alice did it" or "No, it's still dirty."
*   **Schema:**
    ```python
    class VerifyChore(BaseModel):
        log_id: str           # Extracted from conversation context
        decision: Literal['APPROVE', 'REJECT']
        reason: str | None
    ```

### B. Onboarding (The Bouncer)
Tools for managing house access.

#### `tool_request_join`
*   **Trigger:** "Join HOUSE123 SecretPass"
*   **Schema:**
    ```python
    class RequestJoin(BaseModel):
        house_code: str
        password: str
        display_name: str
    ```

#### `tool_approve_member`
*   **Trigger:** "Approve Bob" (Admin only)
*   **Schema:**
    ```python
    class ApproveMember(BaseModel):
        target_phone: str
    ```

### C. Information & Queries
These tools allow the agent to read the database.

#### `tool_get_status`
*   **Trigger:** "What do I need to do today?"
*   **Schema:**
    ```python
    class GetStatus(BaseModel):
        target_user_phone: str | None # None = Check whole house
        time_range: Literal['TODAY', 'OVERDUE', 'WEEK']
    ```

#### `tool_get_analytics`
*   **Trigger:** "Who is lazy?" or "Who did the most work?"
*   **Schema:**
    ```python
    class GetAnalytics(BaseModel):
        metric: Literal['CHORE_COUNT_LEADERBOARD', 'COMPLETION_RATE']
        period_days: int = 30
    ```

## 4. Complex Agent Behaviors

### Behavior: The "Robin Hood" Swap
*   **Scenario:** User A says "I did User B's chore."
*   **Logic:** Agent identifies `is_swap=True`. Agent confirms: "Logged. I have notified [User B] that you covered for them."

### Behavior: Conflict Handling
*   **Scenario:** User attempts to log a chore that is already marked CONFLICT.
*   **Logic:** Tool returns error `Chore is in CONFLICT state`. Agent replies: "I cannot log this. The 'Kitchen' task is currently disputed. Please resolve the vote first."