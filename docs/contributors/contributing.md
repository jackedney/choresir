# Contribution Guidelines

This guide covers contributing to WhatsApp Home Boss, including commit standards and the PR process.

## Getting Started

1. Read the [Project Context](context.md) and [Toolchain & Style](toolchain.md) for coding standards and architectural patterns
2. Follow the [Development Workflow](development.md) for local setup
3. Ensure your code passes all [Code Quality](code-quality.md) checks

## Branch Strategy

### Branch Naming

Use descriptive branch names:

```bash
feature/add-personal-chore-tracker
fix/webhook-idempotency-bug
docs/update-api-documentation
refactor/extract-ledger-service
```

Prefixes:

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions or changes

### Branch Protection

The `main` branch is protected. All changes must go through pull requests.

## Commit Standards

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Maintenance tasks (dependencies, configuration)

### Scopes

Common scopes include:

- `agents` - Agent logic and tools
- `services` - Business logic services
- `interface` - FastAPI routes and adapters
- `core` - Configuration, logging, database client
- `domain` - Pydantic models and entities
- `tests` - Test code
- `docs` - Documentation

### Examples

**Feature commit:**

```text
feat(agents): add personal chore tracking

Implements personal chore management with:
- Private chore creation and tracking
- Optional accountability assignment
- Flexible scheduling (one-time and recurring)

Closes #123
```

**Bug fix commit:**

```text
fix(interface): resolve webhook idempotency issue

Processed message IDs were not being checked correctly,
causing duplicate AI responses. Fixed by adding
proper memoization.

Fixes #456
```

**Documentation commit:**

```text
docs(contributors): add contribution guidelines

Added comprehensive guide for contributors including
commit standards, PR process, and code review checklist.
```

### Commit Checklist

Before committing, verify:

- [ ] Code follows [Toolchain & Style](toolchain.md) and [Code Quality](code-quality.md) conventions
- [ ] All code quality checks pass (`ruff format .`, `ruff check . --fix`, `ty check src`)
- [ ] All tests pass (`pytest`)
- [ ] Commit message follows conventional commits format
- [ ] No TODO comments in code
- [ ] All functions have type hints

## Pull Request Process

### Creating a Pull Request

1. **Update your branch:**

```bash
git fetch origin
git rebase origin/main
```

1. **Push to GitHub:**

```bash
git push origin feature/your-branch-name
```

1. **Create PR on GitHub:**
   - Go to the repository on GitHub
   - Click "Pull requests" → "New pull request"
   - Select your branch
   - Fill in the PR template

### Pull Request Template

```markdown
## Description
Brief description of the changes made.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring
- [ ] Performance improvement

## Related Issue
Closes #123

## Changes Made
- List major changes here
- Include architectural decisions
- Note any breaking changes

## Testing
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] Manual testing completed (if applicable)

## Checklist
- [ ] Code follows AGENTS.md conventions
- [ ] All code quality checks pass
- [ ] Documentation updated (if needed)
- [ ] No TODOs left in code
- [ ] Type hints added for all functions
```

### PR Review Process

1. **Automated Checks:**
   - CI runs all quality checks automatically
   - All checks must pass before merge
   - Failed checks block merge

2. **Code Review:**
   - At least one maintainer approval required
   - Reviewers check: code quality, architecture, testing
   - Address review comments in commits or replies

3. **Merge Requirements:**
   - All automated checks pass
   - At least one approval
   - No unresolved conversations
   - Up-to-date with main branch

## Code Review Guidelines

### For Authors

- Keep PRs focused and small when possible
- Include tests for new functionality
- Update documentation for user-facing changes
- Respond to review comments promptly
- Address all review comments before requesting merge

### For Reviewers

- Check code follows [Toolchain & Style](toolchain.md) and [Code Quality](code-quality.md) conventions
- Verify tests cover new functionality
- Look for security issues
- Check for performance regressions
- Provide constructive, specific feedback
- Request changes if quality standards not met

### Common Review Feedback

**Type hints missing:**

```python
# BAD
def process(data):
    return transform(data)

# GOOD
def process(data: dict[str, Any]) -> dict[str, Any]:
    return transform(data)
```

**Direct PocketBase usage:**

```python
# BAD: Direct PocketBase import
from pocketbase import PocketBase
pb = PocketBase("http://localhost:8090")

# GOOD: Use DatabaseService
from src.services.database import DatabaseService
db = DatabaseService()
```

**Missing return type:**

```python
# BAD
def get_chore(id: str):
    return db.get(id)

# GOOD
def get_chore(id: str) -> Chore:
    return db.get(id)
```

## Release Process

Releases are managed by maintainers:

1. Version bump in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag: `git tag v0.2.0`
4. Push tag: `git push origin v0.2.0`
5. GitHub Actions creates release

## Questions?

- Check [Project Context](context.md) and [Toolchain & Style](toolchain.md) for coding standards
- Review [Development Workflow](development.md) for setup
- See existing PRs for examples
- Open an issue to discuss major changes

## Recognition

All contributors are acknowledged in the project documentation. Thank you for helping improve WhatsApp Home Boss!
