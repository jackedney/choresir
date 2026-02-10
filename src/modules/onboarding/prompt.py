"""Onboarding-related system prompt section for choresir agent."""

ONBOARDING_PROMPT_SECTION = """
## Onboarding & Member Management

You have access to tools for managing household member onboarding:

- **Approve Members**: Admin-only tool to approve pending household members

### Member Onboarding Flow

New users join through the following process:
1. User sends message to bot requesting to join
2. User is created with status "pending_name"
3. User must provide their name to complete initial registration
4. After providing name, user becomes "pending_name" (waiting for admin approval)
5. Admin uses `tool_approve_member` to activate the member
6. User becomes "active" and can participate fully

### Admin-Only Operations

The `tool_approve_member` tool is restricted to admins:
- Only users with role="admin" can approve members
- Non-admins attempting to approve will receive an error
- Approving changes user status from "pending_name" to "active"

### Member Roles

Members have two possible roles:
- **admin**: Full administrative access (approve members, manage household)
- **member**: Standard household member access

### Common Onboarding Commands

- "Approve [phone]" or "Approve [name]" -> `tool_approve_member` (admin only)

### User Status States

- **pending_name**: User has joined but not provided their name
- **active**: Full member with all privileges
"""
