# Feature Request: House Fund Ledger

## Problem
Financial disputes are a major source of household friction. Roommates often forget who paid for what (utilities, internet, supplies), leading to awkward "venmo me" conversations or resentment.

## Proposed Solution
Implement a lightweight ledger system (similar to Splitwise) directly in the chat. Users can log shared expenses, and the bot tracks balances.

## User Stories
*   As a user, I want to say "I paid $50 for internet" and have it split among all active members.
*   As a user, I want to ask "Who do I owe?" and get a summary of my debts.
*   As a user, I want to say "I settled up with Alice" to clear a debt.

## Technical Implementation

### Schema Changes
New collection `expenses`:
*   `payer`: relation (users)
*   `amount`: number
*   `description`: text
*   `split_with`: relation (users, multiple) - default to all active
*   `date`: datetime

New collection `settlements`:
*   `payer`: relation (users)
*   `receiver`: relation (users)
*   `amount`: number
*   `date`: datetime

### New Tools
*   `tool_log_expense(amount: float, description: str, payer_id: str)`
*   `tool_get_balances()`: Calculates net balances based on expenses and settlements.
*   `tool_settle_up(receiver_id: str, amount: float)`

### Agent Behavior
*   Identify monetary amounts and context ("bought pizza for $20").
*   Ask for clarification on splits if ambiguous (e.g., "Was that for everyone?").
