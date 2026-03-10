# Project Specification

## Purpose

Choresir is a household operating system accessed through WhatsApp group chat. It enables household members to coordinate shared and personal tasks, track accountability, and maintain household order through peer verification — all via natural language conversation with an AI agent.

## Requirements

### Messaging Interface

1. The system must accept and respond to natural language messages from household members via a WhatsApp group chat.
2. The system must process messages asynchronously, acknowledging receipt before completing processing.
3. The system must deduplicate messages so that no single message is processed more than once.
4. The system must enforce per-user rate limits on message processing.
5. The system must validate the authenticity of incoming messages before processing them.

### Task Management

6. The system must support creating tasks with a title, optional description, optional deadline, and optional recurrence schedule.
7. Tasks must be either shared (visible to all household members) or personal (visible only to the owner).
8. Each task must have an assignee who is responsible for completing it.
9. The system must support reassigning tasks between household members.
10. The system must support three verification modes for task completion: no verification, peer verification (any other member), and partner verification (a specific designated member).
11. When verification is required, a completion claim must be approved or rejected by an eligible verifier before the task is marked complete.
12. A member must not be able to verify their own completion claim.
13. Rejected completion claims must return the task to its uncompleted state.
14. Verified tasks with a recurrence schedule must automatically reset and calculate their next deadline.
15. Shared task deletion must require approval from another household member before taking effect. Personal task deletion by the task owner does not require approval.
16. Any household member may claim and complete another member's task, limited to a configurable maximum number of takeovers per week per user.
17. The system must track task completion history including who completed it, who verified it, and any feedback.

### Onboarding & Membership

18. New members joining the designated WhatsApp group must be automatically registered with a pending status.
19. The system must prompt new members for their name before granting full access.
20. Members must have one of two roles: admin or member.
21. The system must provide a web-based admin interface for managing members, managing tasks (viewing, editing, and deleting), household configuration, and WhatsApp session setup.

### Analytics & Notifications

22. The system must provide individual task statistics including completion counts and rankings.
23. The system must generate household-level analytics including leaderboards and completion rates.
24. The system must identify and report overdue tasks.
25. The system must send scheduled reminders for overdue and upcoming tasks.
26. The system must send a daily household activity summary.
27. The system must send a weekly leaderboard report.

### Reliability & Security

28. The system must continue to function if the AI model is temporarily unavailable, using retry logic with backoff.
29. The system must validate the authenticity of all incoming webhook requests using a shared secret.
30. The system must enforce rate limits to prevent abuse at both the global and per-user level.
31. The admin interface must require authentication and protect against cross-site request forgery.

## Constraints

1. The system must operate entirely through WhatsApp as the user-facing interface — no mobile app, web app, or other chat platform for end users.
2. The system must use a single SQLite database as its sole data store.
3. The system must support a single household per deployment.
4. The system must run as a self-hosted deployment (not a multi-tenant SaaS).

## Out of Scope

1. Pantry inventory and shopping list management.
2. Multi-household or multi-tenant support.
3. User-facing interfaces beyond WhatsApp (the admin web interface is for administrators only, not end users).
4. Media message processing (images, videos, documents).
5. Integration with external calendar or task management services.
