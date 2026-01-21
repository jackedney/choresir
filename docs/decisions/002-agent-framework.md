# ADR 002: Agent Framework and Prompt Design

## Status

Accepted

## Context

The choresir application uses a conversational AI agent to interpret and execute household management commands via WhatsApp. The agent must handle multiple domains (chores, verification, analytics, pantry management) while maintaining a consistent, functional tone appropriate for household task coordination.

Key requirements include:
- Concise, WhatsApp-friendly responses (mobile context)
- Strict functional neutrality (no unnecessary praise or fluff)
- Support for multiple household management domains
- Clear entity anchoring to prevent ambiguity
- Graceful handling of ambiguous requests
- Safety confirmations for destructive actions

## Decision

We will use a **modular tool-based agent architecture** with a carefully engineered system prompt that enforces functional neutrality and context awareness.

### Agent Architecture

**Core Components:**
1. **System Prompt Template**: Defines agent personality, directives, and available capabilities
2. **Tool Registry**: Modular tools organized by domain (onboarding, chores, verification, analytics, pantry)
3. **Context Injection**: Dynamic context (user identity, role, time, household members) injected per request
4. **Pydantic AI Framework**: Type-safe tool definitions with structured outputs

**Tool Organization:**
- `onboarding_tools`: Join requests, member approval (admin-only)
- `chore_tools`: Chore creation, logging completions
- `verification_tools`: Chore verification, status queries
- `analytics_tools`: Leaderboards, completion rates, personal stats
- `pantry_tools`: Inventory management, shopping lists

## Rationale

### Functional Neutrality
The household chore context requires a pragmatic, fact-based tone. Over-enthusiastic responses ("Great job!") or unnecessary commentary creates friction in a utility-focused application. The system prompt explicitly enforces:
- No praise or judgment
- Factual reporting only
- Conciseness (2-3 sentences max)

### Entity Anchoring
Household management involves multiple people and chores. The agent must never make assumptions about which person or chore is being referenced. The system prompt mandates:
- Always reference entities by ID or phone number
- Ask clarifying questions when ambiguous
- Provide options rather than guessing

### Context Injection
Rather than maintaining long conversation histories, we inject relevant context (user identity, household members, current time) into each request. This approach:
- Reduces token costs (no long histories)
- Prevents context drift
- Ensures fresh, accurate context per request
- Simplifies state management

### Modular Tool Design
Organizing tools by domain (chores, verification, analytics, pantry) enables:
- Clear separation of concerns
- Easy addition of new feature domains
- Independent testing of tool groups
- Maintainable codebase as features grow

## Consequences

### Positive
- Consistent, professional tone across all interactions
- Clear mental model for users (functional assistant, not chatbot)
- Easy to extend with new feature domains
- Reduced ambiguity through explicit entity anchoring
- Lower token costs (short context, no history)
- Type-safe tool definitions prevent runtime errors

### Negative
- May feel "cold" to users expecting warmer interactions
- Requires careful prompt engineering for new features
- Stateless design requires context rebuilding per request
- No memory of previous conversations

### Neutral
- Agent personality is opinionated (by design)
- Requires user adaptation to functional tone
- Prompt maintenance needed as features evolve

## Implementation Notes

### System Prompt Structure
```
CORE DIRECTIVES:
1. No fluff. Be concise. Use WhatsApp-friendly formatting (max 2-3 sentences).
2. Strict neutrality. No praise, no judgment. Report facts only.
3. Entity anchoring. Always reference entities by ID/phone number, not assumptions.
4. Confirm before destructive actions (delete chore, ban user).
5. If ambiguous, ask clarifying questions with options.

CURRENT CONTEXT:
- User: {user_name} ({user_phone})
- Role: {user_role}
- Time: {current_time}

HOUSEHOLD MEMBERS:
{member_list}

AVAILABLE ACTIONS:
[Tool categories listed here]
```

### Adding New Feature Domains
1. Create new tool module in `src/agents/tools/`
2. Define tools with Pydantic models
3. Import tools in `choresir_agent.py` (auto-registers)
4. Update `AVAILABLE ACTIONS` section in system prompt

### Testing Strategy
- Unit tests for individual tools
- Integration tests with mock dependencies
- Prompt testing for tone consistency
- End-to-end tests via WhatsApp webhook

## Revisions

### Revision 1: Gamification Integration (January 2025)

**Change**: Added personal stats and ranking functionality to support weekly leaderboard feature.

**Prompt Modification**:
```diff
AVAILABLE ACTIONS:
You have access to tools for:
- Onboarding: Request to join household, approve members (admin only)
- Chore Management: Define new chores, log completions
- Verification: Verify chore completions, query status
- Analytics: Get leaderboards, completion rates, overdue chores
+ - Stats: Get personal stats and ranking (triggers: "stats", "score", "how am I doing")
```

**Rationale**:
- Weekly leaderboard feature required personal stats queries
- Explicit trigger keywords help users discover stats functionality
- Separated from general analytics for clarity

**Tool Impact**:
- Added tools: `get_user_stats()`, `get_user_ranking()`
- Enhanced `analytics_tools` module

### Revision 2: Smart Pantry Integration (January 2025)

**Change**: Added inventory and shopping list management capabilities.

**Prompt Modification**:
```diff
AVAILABLE ACTIONS:
You have access to tools for:
- Onboarding: Request to join household, approve members (admin only)
- Chore Management: Define new chores, log completions
- Verification: Verify chore completions, query status
- Analytics: Get leaderboards, completion rates, overdue chores
- Stats: Get personal stats and ranking (triggers: "stats", "score", "how am I doing")
+ - Pantry & Shopping: Manage inventory, add items to shopping list, checkout after shopping
```

**Rationale**:
- Expanded household management scope beyond chores
- Natural companion feature to chore coordination
- Maintains functional tone (inventory management, not recipe suggestions)

**Tool Impact**:
- Added new module: `pantry_tools`
- Tools: `add_pantry_item()`, `remove_pantry_item()`, `get_pantry_inventory()`, `add_to_shopping_list()`, `checkout_shopping_list()`

**Design Considerations**:
- Pantry tools follow same functional neutrality as chore tools
- No recipe suggestions or meal planning (out of scope)
- Focus on inventory tracking and shopping coordination

## Related ADRs

- [ADR 001: Technology Stack](001-stack.md) - Core technology choices including WhatsApp provider (Twilio)
- [ADR 012: Natural Language Processing Approach](012-nlp-approach.md) - LLM backend powering the agent
- [ADR 014: Robin Hood Protocol](014-robin-hood-protocol.md) - Feature requiring agent interpretation of chore swaps

## References

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- Agent Implementation: `src/agents/choresir_agent.py`
- Tool Modules: `src/agents/tools/`
- Gamification PR: #[number] (January 2025)
- Smart Pantry PR: #27 (January 2025)
