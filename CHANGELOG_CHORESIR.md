# Changelog

All notable changes to the choresir project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Intelligent Error Notifications** (2026-01-18)
  - Automatic error classification system for API failures (quota exceeded, rate limits, auth errors, network issues)
  - User-friendly error messages that hide technical details and provide actionable guidance
  - Admin WhatsApp notifications for critical errors (quota exceeded, authentication failures)
  - Rate limiting for admin notifications to prevent spam (configurable cooldown period, default 60 minutes)
  - Graceful degradation when notification delivery fails
  - Configuration options: `ENABLE_ADMIN_NOTIFICATIONS`, `ADMIN_NOTIFICATION_COOLDOWN_MINUTES`
  - Comprehensive test coverage in `tests/unit/test_errors.py`, `tests/unit/test_admin_notifier.py`, and `tests/integration/test_openrouter_errors.py`
  - Documentation in `docs/ERROR_HANDLING.md`

## [1.0.0] - 2026-01-16

### Added
- **Core System** (MVP Complete)
  - FastAPI application with health check endpoint
  - PocketBase integration for data persistence
  - WhatsApp Cloud API integration via webhooks
  - Environment-based configuration system
  - Pydantic Logfire instrumentation for observability

- **User Management**
  - User onboarding with house code and password validation
  - Admin approval workflow for new members
  - User roles (admin, member) with permission enforcement
  - User status tracking (pending, active, banned)

- **Chore Management**
  - Chore creation with flexible recurrence patterns (CRON or "every X days")
  - State machine for chore lifecycle (TODO → PENDING_VERIFICATION → COMPLETED/CONFLICT)
  - Floating schedule system (next deadline calculated from completion time)
  - Assignment to specific users or unassigned pool

- **Verification & Conflict Resolution**
  - Peer verification system for completed chores
  - Conflict voting mechanism when verification is rejected
  - Automatic deadlock detection for even-population households
  - Anonymous voting to prevent bias

- **AI Agent (choresir)**
  - Pydantic AI agent powered by OpenRouter (Claude 3.5 Sonnet)
  - Natural language interface for all household management tasks
  - Context-aware responses with user information and household state
  - Strict neutrality and concise communication style
  - Tool-based architecture for onboarding, chore management, verification, and analytics

- **Analytics & Reporting**
  - Leaderboard showing completion counts per user
  - Completion rate tracking (on-time vs. overdue)
  - Overdue chore monitoring
  - Weekly leaderboard reports

- **Pantry Management**
  - Inventory tracking for household items
  - Shopping list management
  - Bulk checkout after shopping trips

- **Scheduled Tasks**
  - Daily chore reminders (8am)
  - Daily completion reports (9pm)
  - Weekly leaderboard reports (8pm Sunday)

- **Testing Infrastructure**
  - Ephemeral PocketBase instances for integration tests
  - Comprehensive test coverage for core workflows
  - Unit tests for all services and utilities

- **DevOps**
  - Railway deployment configuration
  - Local development setup with ngrok for webhook testing
  - Schema synchronization on application startup

### Documentation
- Architecture Decision Records (ADRs)
- Development roadmap with task dependencies
- Local development setup guide
- API integration documentation

---

## Release Notes

### v1.0.0 - MVP Launch
The first production-ready release of choresir, a WhatsApp-based household chore management system. This release includes all core functionality for onboarding, chore tracking, verification, conflict resolution, and analytics.

**Key Features:**
- Natural language interface via WhatsApp
- AI-powered chore management with Claude 3.5 Sonnet
- Democratic verification and conflict resolution
- Automated reminders and reports
- Comprehensive observability with Pydantic Logfire

**Known Limitations:**
- In-memory rate limiting (resets on service restart)
- Basic error handling (improved in unreleased version)
- Single household per deployment

---

## Migration Guide

### Upgrading from Pre-1.0.0

If you were using a pre-release version of choresir, please note:

1. **Database Schema:** Run `python -m src.core.schema` to sync the latest schema
2. **Environment Variables:** Review `.env.example` for new required variables
3. **PocketBase:** Ensure you're running PocketBase v0.23.0 or later

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [PocketBase](https://pocketbase.io/) - Database and backend
- [Pydantic AI](https://ai.pydantic.dev/) - AI agent framework
- [OpenRouter](https://openrouter.ai/) - LLM API access
- [Twilio](https://www.twilio.com/) - WhatsApp messaging
- [Pydantic Logfire](https://pydantic.dev/logfire) - Observability

---

[Unreleased]: https://github.com/yourusername/choresir/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yourusername/choresir/releases/tag/v1.0.0
