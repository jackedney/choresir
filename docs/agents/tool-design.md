# Tool Design

This page describes tool design patterns for Pydantic AI agents.

## Explicit Arguments

All tools must take a single Pydantic Model as an argument (or named args typed
with Pydantic primitives) to ensure schema generation works perfectly with the LLM.

## Error Handling

Tools must return descriptive error strings (e.g., "Error: Chore not found") rather
than raising exceptions.

## Example

```python
def tool_log_chore(params: LogChoreParams) -> str:
    try:
        ...
    except ChoreNotFound:
        return "Error: Chore not found"
```
