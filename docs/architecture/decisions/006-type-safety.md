# ADR 006: Type Safety and Type Checking

## Status

Accepted

## Context

Python is a dynamically typed language, which can lead to runtime errors that could be caught earlier with static type checking. The project uses type hints throughout the codebase, but needs a type checker to validate these hints and catch type-related issues during development.

## Decision

We will use `ty` as our type checker for this project.

### Type Checker Configuration

- **Tool**: `ty` is installed and available in the project
- **Installation**: Managed via uv package manager
- **Usage**: Run type checking using one of the following methods:
  1. `uv run ty` - Run ty through uv (recommended)
  2. Activate uv environment first, then run `ty`

### Running Type Checks

```bash
# Recommended: Run directly with uv
uv run ty

# Alternative: Activate environment first
source .venv/bin/activate  # or your uv environment activation method
ty
```

## Consequences

### Positive

- **Early error detection**: Catch type-related bugs during development rather than at runtime
- **Better IDE support**: Type hints enable better autocomplete and refactoring tools
- **Documentation**: Type hints serve as inline documentation for function signatures
- **Refactoring confidence**: Type checker validates that changes maintain type correctness across the codebase
- **Simple workflow**: Using uv makes type checking straightforward

### Negative

- **Development overhead**: Developers must maintain type hints and address type checker warnings
- **Learning curve**: Team members need to understand Python's type system and type hints
- **Build process**: Type checking adds an additional step to the development workflow

## Implementation

- Type hints should be added to all new code
- Existing code should be gradually typed as it's modified
- Type checking should be part of the CI/CD pipeline
- Type errors should be addressed before merging pull requests

## Notes

- `ty` is already installed in the project dependencies
- Requires uv environment to be active or use `uv run` prefix
- Type checking configuration can be customized as needed

## References

- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [Python typing module documentation](https://docs.python.org/3/library/typing.html)
