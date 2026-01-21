# Architecture Decision Records (ADRs)

This directory contains all architectural decisions for the WhatsApp Home Boss project.

## Index

### Core Architecture (001-010)
- [001: Technology Stack](001-stack.md) - Core technology choices (includes WhatsApp provider)
- [002: Agent Framework](002-agent-framework.md) - Pydantic AI agent design and prompt engineering
- [003: Verification Protocol](003-verification.md) - Chore verification approach
- [004: Conflict Resolution](004-conflict.md) - Handling disputes
- [005: Model Selection](005-models.md) - LLM model choices
- [006: Code Standards](006-standards.md) - Development standards
- [007: Operations](007-operations.md) - Operational decisions
- [008: Gamification](008-gamification.md) - Gamification features
- [009: Interactive Verification](009-interactive-verification.md) - Enhanced verification
- [010: Smart Pantry](010-smart-pantry.md) - Pantry management feature

### Infrastructure & Integration (011-016)
- [011: Version Management](011-version-management.md) - Version control strategy
- [012: NLP Approach](012-nlp-approach.md) - Natural language processing
- [013: Redis Caching](013-redis-caching.md) - Caching strategy
- [014: Robin Hood Protocol](014-robin-hood-protocol.md) - Chore swapping feature
- [015: Type Safety](015-type-safety.md) - Type system approach
- [016: Conversational House Joining](016-conversational-house-joining.md) - Onboarding flow

## ADR Format

Each ADR follows this structure:
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Date**: When the decision was made
- **Context**: The problem and constraints
- **Decision**: What was decided
- **Consequences**: Positive, negative, and mitigation strategies

## Creating New ADRs

1. Use the next available number (017, 018, etc.)
2. Follow the naming convention: `NNN-descriptive-name.md`
3. Include all required sections
4. Update this index

## Notes

- ADR-001 consolidates the original stack decision with the WhatsApp provider selection (formerly separate ADR-011)
- ADR-002 is the comprehensive agent framework document (supersedes the original brief Pydantic AI selection doc)
