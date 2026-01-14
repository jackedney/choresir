# Agent Architecture

## Overview
Based on ADR 002 (Pydantic AI), the system will not use a complex graph of autonomous agents (like LangGraph). Instead, it will use a **Router-Tool Pattern**. 

A single "Main Agent" acts as the interface, equipped with context-aware tools that represent the specialized logic of the application.

## Agent Persona: "The House Manager"
The LLM system instruction will adopt the persona of a **firm but fair House Manager**.
*   **Tone:** Professional, concise, slightly bureaucratic but polite.
*   **Goal:** Ensure chores are done and recorded accurately.
*   **Anti-Goal:** It should not engage in small talk or therapy. It focuses on the state of the house.

## Tool Groups (Functional Domains)

Instead of separate "Agents," we group Pydantic AI `RunContext` tools into domains:

### 1. The Ledger (Chore Management)
*   **Context:** Read/Write access to PocketBase `chores` collection.
*   **Tools:**
    *   `log_chore_completion(chore_id: str)`: Marks a chore as PENDING_VERIFICATION.
    *   `define_new_chore(title: str, description: str, cron_schedule: str, default_assignee_id: Optional[str])`: Creates a new chore record from natural language.
    *   `get_my_pending_chores(user_id: str)`
    *   `snooze_chore(chore_id: str, duration_hours: int)`

### 2. The Auditor (Verification Protocol - ADR 003)
*   **Context:** State machine transitions.
*   **Tools:**
    *   `request_verification(chore_id: str)`: Transitions `TODO` -> `PENDING_VERIFICATION`. Notifies other users.
    *   `approve_chore(chore_id: str, verifier_id: str)`: Transitions `PENDING` -> `COMPLETED`.
    *   `reject_chore(chore_id: str, verifier_id: str, reason: str)`: Transitions `PENDING` -> `CONFLICT`.

### 3. The Jury (Conflict Resolution - ADR 004)
*   **Context:** Access to `users` collection to count active population.
*   **Tools:**
    *   `initiate_vote(conflict_id: str)`: Calculates Odd/Even logic.
    *   `cast_vote(conflict_id: str, user_id: str, vote: bool)`
    *   `resolve_deadlock(conflict_id: str)`: Only available after manual verbal resolution.

### 4. The Bouncer (Onboarding - ADR 007)
*   **Context:** User management and access control.
*   **Tools:**
    *   `request_join(phone_number: str, house_code: str, password: str)`: Checks env vars, creates "pending" user.
    *   `approve_member(target_user_phone: str)`: Admin-only. Activates a pending user.

## Interaction Flow

1.  **Inbound:** WhatsApp Webhook receives text.
2.  **Identification:** Lookup User ID via Phone Number in PocketBase.
3.  **Routing:** 
    *   The Agent analyzes the text.
    *   If the user says "I did the dishes", the Agent calls `log_chore_completion`.
    *   If the user says "Add a chore to Vacuum every Friday at 5pm", the Agent calls `define_new_chore`.
    *   If the user replies "Approved" to a notification, the Agent calls `approve_chore`.
4.  **Response:** The Agent generates a confirmation message based on the Tool output.

## System Prompt Strategy
> "You are HomeBase, a house management assistant. You manage the database of chores. You do not hallucinate completions. You enforce the Verification Protocol: no chore is done until a second pair of eyes sees it."
