# Naming Conventions

This page describes naming conventions for Pydantic AI agents in WhatsApp Home Boss.

## Agents

Use snake case for agent variable names and function references (e.g., `household_manager`).

### Agent Examples

- `choresir_agent` - Main household management agent
- `onboarding_agent` - User onboarding agent
- `analytics_agent` - Data analytics agent

### Agent Rationale

Snake case is used for agents to follow Python naming conventions for variables and
functions. This makes agent instances easier to reference in code and improves
readability.

## Tools

Use snake case, prefixed with `tool_` for tool functions (e.g., `tool_log_chore`).

### Tool Examples

- `tool_log_chore` - Log a chore completion
- `tool_define_chore` - Create a new chore
- `tool_request_join` - Request to join household
- `tool_approve_member` - Approve a pending member

### Tool Rationale

The `tool_` prefix makes it clear which functions are registered as tools with the
Pydantic AI agent. This convention helps distinguish tool functions from regular
utility functions in the same module.

## Models

Use PascalCase for Pydantic model classes used as tool parameters (e.g.,
`LogChore`).

### Model Examples

- `LogChore` - Parameters for logging a chore completion
- `DefineChore` - Parameters for defining a new chore
- `RequestJoin` - Parameters for joining the household
- `ApproveMember` - Parameters for approving a member

### Model Rationale

PascalCase (also known as UpperCamelCase) is the standard Python convention for
class names. Using PascalCase for Pydantic models makes them instantly recognizable
as data structures rather than functions or variables.

### Negative Case

Incorrect model naming that should be avoided:

```python
# Bad - uses snake case for model class
class log_chore(BaseModel):
    """Bad naming convention."""
    pass

# Bad - no descriptive name
class Params1(BaseModel):
    """Non-descriptive naming."""
    pass

# Good - uses PascalCase with descriptive name
class LogChore(BaseModel):
    """Correct naming convention."""
    pass
```
