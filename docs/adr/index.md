# Architectural Decision Records

This section contains all Architectural Decision Records (ADRs) for WhatsApp Home Boss.

ADRs document significant architectural decisions made throughout the project's development, including the context, decision, consequences, and alternatives considered.

## Chronological Index

### Core Architecture (001-010)

- [ADR 001: Technology Stack](001-stack.md) - Adoption of "Indie Stack" (Python + PocketBase + Twilio WhatsApp)
- [ADR 002: Agent Framework and Prompt Design](002-agent-framework.md) - Pydantic AI agent architecture and system prompt engineering
- [ADR 003: Human-in-the-Loop Verification Protocol](003-verification.md) - Mandatory verification state machine for chore completion
- [ADR 004: Deterministic Conflict Resolution](004-conflict.md) - Math-based jury system for dispute resolution
- [ADR 005: Model Selection via OpenRouter](005-models.md) - LLM model selection and gateway strategy
- [ADR 006: Repository Standards & Engineering Practices](006-standards.md) - Astral stack (ruff, uv, ty) and coding conventions
- [ADR 007: Operational Strategy & Data Schema](007-operations.md) - Onboarding, data models, WhatsApp integration, testing strategy
- [ADR 008: Gamification & Analytics](008-gamification.md) - Weekly leaderboards, personal stats, and engagement features
- [ADR 009: Interactive Button-Based Verification](009-interactive-verification.md) - WhatsApp quick reply buttons for verification
- [ADR 010: Smart Pantry & Grocery Management](010-smart-pantry.md) - Inventory tracking and shared shopping lists

### Infrastructure & Integration (011-016)

- [ADR 011: Version Management Strategy](011-version-management.md) - Environment parity and coordinated dependency upgrades
- [ADR 012: Natural Language Processing Approach](012-nlp-approach.md) - Pydantic AI with OpenRouter for command interpretation
- [ADR 013: Redis Caching for Leaderboard Performance](013-redis-caching.md) - Caching strategy for analytics performance
- [ADR 014: Robin Hood Protocol](014-robin-hood-protocol.md) - Chore takeover system with optional reciprocal exchange
- [ADR 015: Type Safety and Type Checking](015-type-safety.md) - Using `ty` for static type checking
- [ADR 016: Conversational House Joining Flow](016-conversational-house-joining.md) - Multi-step conversational onboarding (proposed)

### Personal Features (017+)

- [ADR 019: Personal Chores System](019-personal-chores.md) - Privacy-respecting personal goal tracking with optional partner verification

## ADR Format

Each ADR follows this structure:

- **Status**: Proposed, Accepted, Deprecated, Superseded, Partially Implemented
- **Date**: When the decision was made
- **Context**: The problem and constraints
- **Decision**: What was decided
- **Consequences**: Positive, negative, and neutral impacts
- **Related ADRs**: Links to related architectural decisions
- **References**: External documentation or implementation links

## Creating New ADRs

To create a new ADR:

1. Use the [ADR Template](template.md) as a starting point
2. Use the next available number (020, 021, etc.)
3. Follow the naming convention: `NNN-descriptive-name.md`
4. Include all required sections
5. Update this index with a link to the new ADR

## Notes

- ADR-001 consolidates the original stack decision with the WhatsApp provider selection (formerly separate ADR-011)
- ADR-002 is the comprehensive agent framework document (supersedes the original brief Pydantic AI selection doc)
- Some ADRs may have status "Partially Implemented" or "Proposed" if they are still in progress
