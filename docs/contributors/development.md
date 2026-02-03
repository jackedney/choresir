# Development Workflow

This guide covers the development workflow for WhatsApp Home Boss.

## Local Development Environment Setup

### Prerequisites

- **Python 3.12+** - Required runtime
- **uv** - Fast Python package manager
- **Redis** - Required for caching (optional with Docker Compose)
- **PocketBase** - Self-hosted database
- **Docker** (recommended) - For running Redis and WAHA services
- **Git** - Version control

### Installation

1. **Clone the repository:**

```bash
git clone https://github.com/yourusername/whatsapp-home-boss.git
cd whatsapp-home-boss
```

1. **Install dependencies with uv:**

```bash
uv sync
```

1. **Download PocketBase:**

```bash
# macOS
curl -L https://github.com/pocketbase/pocketbase/releases/download/v0.23.4/pocketbase_0.23.4_darwin_amd64.zip -o pocketbase.zip
unzip pocketbase.zip
mv pocketbase ./pocketbase
chmod +x ./pocketbase
```

1. **Configure environment:**

```bash
cp .env.example .env
# Edit .env with your configuration
```

1. **Start Redis:**

```bash
# Option A: Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Option B: Docker Compose
docker-compose up -d redis
```

## Running the Application

### Development Mode

For local development with auto-reload:

```bash
# Terminal 1: Start PocketBase
./pocketbase serve

# Terminal 2: Start FastAPI dev server
uv run fastapi dev src/main.py

# Terminal 3: Start WAHA (if using)
docker run -p 3000:3000 devlikeapro/waha
```

### Full Stack with Docker Compose

For a complete development environment:

```bash
docker-compose up -d
```

This starts all services: Redis, WAHA, and the application.

## Testing

Run tests with pytest:

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_agents.py

# Run with verbose output
uv run pytest -v

# Run specific test
uv run pytest tests/test_agents.py::test_create_chore

# Run integration tests only
uv run pytest -m integration
```

### Test Strategy

- **Integration Tests:** Use pytest with ephemeral PocketBase instances
- **No Mocks:** Test against the real (temporary) database binary
- **Async Tests:** pytest-asyncio handles async test execution

## Building

Build the documentation:

```bash
# Serve documentation locally
mkdocs serve

# Build static documentation
mkdocs build
```

## Standard Development Workflow

1. **Create a feature branch:**

```bash
git checkout -b feature/your-feature-name
```

1. **Make your changes:**
   - Write code following AGENTS.md conventions
   - Add tests for new functionality
   - Update documentation if needed

1. **Run quality checks:**

```bash
uv run ruff format .
uv run ruff check . --fix
uv run ty check src
uv run pytest
```

1. **Commit your changes:**

```bash
git add .
git commit -m "feat: add your feature description"
```

1. **Push and create PR:**

```bash
git push origin feature/your-feature-name
# Create pull request on GitHub
```

## Common Development Tasks

### Adding a New Agent

1. Create agent file in `src/agents/`
2. Follow naming conventions: `snake_case` for agents/tools
3. Use Pydantic models for tool parameters
4. Implement dependency injection via `RunContext[Deps]`
5. Add tests in `tests/agents/`

### Adding a New Service

1. Create service module in `src/services/`
2. Use functional patterns (standalone functions, not classes)
3. Enforce keyword-only arguments with `*` for >2 parameters
4. Use Pydantic models for data transfer
5. Add tests in `tests/services/`

### Database Schema Changes

1. Update schema definition in `src/core/schema.py`
2. The schema syncs on application startup
3. No manual migration needed (code-first approach)
4. Test with ephemeral PocketBase instances

## Troubleshooting

### PocketBase won't start

Ensure the `data/pb_data` directory exists:

```bash
mkdir -p data/pb_data
```

### Redis connection refused

Check Redis is running:

```bash
docker ps | grep redis
# Or
redis-cli ping
```

### Type checking errors

Run ty with verbose output:

```bash
uv run ty check src --explain
```

### Tests failing with database errors

Ensure PocketBase is running on port 8090:

```bash
./pocketbase serve
```
