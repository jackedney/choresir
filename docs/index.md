# WhatsApp Home Boss

A WhatsApp-powered household management bot. Python + FastAPI + Pydantic AI + PocketBase.

## Commands

| Action | Example | Notes |
|--------|---------|-------|
| Log chore | "Done dishes" | Triggers verification request |
| Create chore | "Create chore 'Water plants' every 3 days" | Admin only |
| View stats | "Stats" | Personal ranking + household leaderboard |
| Add to shopping list | "Add eggs to list" | Shared household list |
| View shopping list | "What's on the list?" | |
| Personal task | `/personal add go to gym` | Private, not on leaderboard |
| Complete personal | `/personal done gym` | Self-verified or partner-verified |
| Join household | `/house join MyHouse` | Starts onboarding flow |

## Concepts

**Household chores** are shared, visible to all members, require peer verification, and count toward the leaderboard.

**Personal chores** are private (only you see them), optionally verified by an accountability partner, and excluded from household stats.

**Verification**: When you log a household chore, another member must approve it before you get credit.

**Robin Hood**: Take over someone else's overdue chore to help them out.

## Stack

- Python 3.12+ / FastAPI
- PocketBase (SQLite)
- Pydantic AI agents
- WAHA (WhatsApp HTTP API)
- OpenRouter (LLM)
