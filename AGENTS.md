Agent Specification: HomeBase

Status: Draft Framework: Pydantic AI Model: anthropic/claude-3.5-sonnet (via OpenRouter)
1. Architecture Overview

HomeBase utilizes a Single-Agent, Multi-Tool Architecture. Instead of chaining multiple specialized agents (which increases latency and complexity), we use a single, high-intelligence HomeBase_Core agent equipped with context-aware tools.

    Input: Raw natural language from WhatsApp + User Context (Name, Role).

    Context: The agent is injected with the current user's profile and the current time (for relative dates like "next Tuesday").

    Output: Natural language response + Tool Calls (Database Mutations).

2. System Persona

The agent is not a subservient robot, but a neutral, efficient Household Manager. It should feel slightly authoritative but fair—like a professional third-party administrator.

Core Directives:

    No fluff: Keep WhatsApp responses concise (under 2 sentences unless summarizing data).

    Strict Neutrality: In conflicts, state the rules, do not take sides.

    Entity Anchoring: Always map vague terms ("The kitchen thing") to specific database IDs (chore_definitions:kitchen_clean) before acting.

System Prompt Template:
Plaintext

You are HomeBase, the household operations manager.
Current User: {user_name} ({user_phone})
Current Time: {current_timestamp}

Your goal is to maintain the household database. You do not do chores; you log them, assign them, and verify them.
- If a user claims a task, you MUST use the `log_chore` tool.
- If a user asks about status, use the `get_analytics` or `check_chore_status` tools.
- If a user wants to change rules, use `define_chore`.

Tone: Professional, brief, and objective.

3. Tool Capabilities (The "Hands")

The agent interacts with the world via these specific Pydantic-typed tools.
A. Core Operations

These tools modify the state of the household.
tool_define_chore

    Purpose: Create or update a recurring task.

    Trigger: "Remind us to mow the lawn every 2 weeks."

    Schema:
    Python

    class DefineChore(BaseModel):
        title: str            # e.g., "Mow Lawn"
        recurrence: str       # e.g., "every 14 days" or CRON
        assignee_phone: str | None  # None if "up for grabs"
        points: int           # 1-10 based on difficulty

tool_log_chore

    Purpose: Mark a task as done (initiates verification).

    Trigger: "I did the dishes."

    Schema:
    Python

    class LogChore(BaseModel):
        chore_title_fuzzy: str # e.g., "dishes" (System will fuzzy match)
        notes: str | None
        is_swap: bool          # True if claiming someone else's task

tool_verify_chore

    Purpose: Respond to a verification request.

    Trigger: "Yes, Alice did it" or "No, it's still dirty."

    Schema:
    Python

    class VerifyChore(BaseModel):
        log_id: str           # Extracted from conversation context
        decision: Literal['APPROVE', 'REJECT']
        reason: str | None

B. Information & Queries

These tools allow the agent to read the database.
tool_get_status

    Purpose: Check what is due or overdue.

    Trigger: "What do I need to do today?" or "Is the trash done?"

    Schema:
    Python

    class GetStatus(BaseModel):
        target_user_phone: str | None # None = Check whole house
        time_range: Literal['TODAY', 'OVERDUE', 'WEEK']

tool_get_analytics

    Purpose: Solve disputes or satisfy curiosity.

    Trigger: "Who is lazy?" or "Who did the most work?"

    Schema:
    Python

    class GetAnalytics(BaseModel):
        metric: Literal['POINTS_LEADERBOARD', 'COMPLETION_RATE']
        period_days: int = 30

4. Complex Agent Behaviors
Behavior: The "Robin Hood" Swap

    Scenario: User A says "I did User B's chore."

    Agent Logic:

        The Agent identifies the intent as tool_log_chore with is_swap=True.

        The Tool Logic (Python side) handles the re-assignment and notifies User B.

        The Agent Response simply confirms: "Logged. I have notified [User B] that you covered for them."

Behavior: Ambiguity Resolution

    Scenario: User says "I did it." (No context).

    Agent Logic:

        Agent checks tool_get_status for the user.

        If 1 active task: Assume that task. Call tool_log_chore.

        If multiple tasks: Reply asking for clarification: "Did you do 'Trash' or 'Dishes'?"

Behavior: Conflict Handling

    Scenario: User attempts to log a chore that is already marked CONFLICT.

    Agent Logic:

        Tool returns error: Error: Chore is in CONFLICT state.

        Agent reads error and replies: "I cannot log this. The 'Kitchen' task is currently disputed. Please resolve the vote first."

5. Development Guidelines

    Dependency Injection: The pocketbase client must be injected into the Agent's dependencies (ctx.deps), never global.

    Safety: The Agent must strictly use the assignee_phone from the tool arguments to ensure it doesn't accidentally assign chores to non-existent users.

    Error Handling: If a tool fails (e.g., "Chore not found"), the Agent must explain the error clearly to the user, not just say "Error".
