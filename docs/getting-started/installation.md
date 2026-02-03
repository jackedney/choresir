# Installation

This guide covers installing WhatsApp Home Boss on your local machine.

## Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.12+ - Required for the application runtime
- uv - Fast Python package manager (install instructions at <https://docs.astral.sh/uv/getting-started/installation/>)
- Git - For cloning the repository
- Docker - Required for Redis cache and WAHA (WhatsApp gateway)
- Docker Compose - For running services with a single command

### Verify Prerequisites

```bash
# Check Python version (must be 3.12+)
python --version

# Check uv installation
uv --version

# Check Docker installation
docker --version
docker-compose --version
```

**Missing a prerequisite?** The installation will fail with a clear error message. For example:

- If Python < 3.12: `Python 3.12 or later is required`
- If Docker missing: `docker: command not found`

## Step 1: Clone the Repository

```bash
git clone https://github.com/jackedney/whatsapp-home-boss.git
cd whatsapp-home-boss
```

## Step 2: Install Python Dependencies

Use `uv` to install all required Python packages:

```bash
uv sync
```

This installs dependencies defined in `pyproject.toml`, including:

- FastAPI (web framework)
- Pydantic AI (agent framework)
- PocketBase SDK (database client)
- APScheduler (task scheduling)
- And other production dependencies

**Verification:** You should see a `.venv` directory created and dependencies installed.

**Error: `uv: command not found`**

Install uv using the official method for your operating system:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Step 3: Download PocketBase

PocketBase is a self-contained Go binary that acts as the database server. Download it using the included task:

```bash
task install-pocketbase
```

This command:

- Detects your operating system and architecture
- Downloads PocketBase v0.23.4 from GitHub releases
- Extracts the binary to the project root
- Makes it executable

**Verification:** Check that the PocketBase binary exists:

```bash
./pocketbase --version
```

**Expected output:** `0.23.4` (or your installed version)

**Error: `task: command not found`**

The `task` command requires [Task runner](<https://taskfile.dev/>). Install it:

```bash
# macOS/Linux
curl -sL https://taskfile.dev/install.sh | sh

# Windows (scoop)
scoop install task

# Or use npm
npm install -g @go-task/task
```

Alternatively, download PocketBase manually:

1. Visit <https://github.com/pocketbase/pocketbase/releases>
2. Download the latest release for your OS/architecture
3. Extract and place `pocketbase` binary in the project root
4. Make it executable: `chmod +x pocketbase` (Linux/macOS)

## Step 4: Start Docker Services

Redis (caching) and WAHA (WhatsApp gateway) run in Docker containers. Start them:

```bash
docker-compose up -d
```

This starts:

- Redis on port 6379 - Caches leaderboard and analytics data
- WAHA on port 3000 - Provides WhatsApp integration

**Verification:** Check that containers are running:

```bash
docker-compose ps
```

**Expected output:** Both `choresir-redis` and `choresir-waha` should show `Up` status.

**Error: `docker-compose: command not found`**

Install Docker Compose:

- Docker Desktop includes Compose (recommended for macOS/Windows)
- Linux: `sudo apt-get install docker-compose` or follow
  [official docs](<https://docs.docker.com/compose/install/>)

### Port already in use

If ports 6379 or 3000 are already in use:

1. Stop conflicting services
2. Modify `docker-compose.yml` to use different ports
3. Update `.env` with the new port mappings

## Step 5: Verify Installation

Run a quick health check to verify everything is installed correctly:

```bash
# Test PocketBase binary
./pocketbase --version

# Test Python dependencies
uv run python --version

# Test Docker services
docker ps | grep -E "redis|waha"
```

All commands should complete without errors.

## Next Steps

After completing installation:

1. [Configuration](./configuration.md) - Set up environment variables
2. [First Run](./first-run.md) - Connect WhatsApp and send your first message

## Troubleshooting

### PocketBase binary fails to run

**Error:** `Exec format error` or similar

**Solution:** You downloaded the wrong architecture. Delete the binary and run
`task install-pocketbase` again, or manually download the correct version from
[GitHub releases](<https://github.com/pocketbase/pocketbase/releases>).

### Docker services fail to start

**Error:** `ERROR: for choresir-redis Cannot start service redis`

**Solution:**

1. Check Docker is running: `docker ps`
2. Check port availability: `lsof -i :6379` and `lsof -i :3000`
3. View container logs: `docker-compose logs redis` or `docker-compose logs waha`

### `uv sync` fails

**Error:** `No matching distribution found` or similar

**Solution:**

1. Ensure Python 3.12+ is installed: `python --version`
2. Update uv: `uv self update`
3. Try with verbose output: `uv sync -v`

### Permission denied on PocketBase binary

**Error:** `permission denied: ./pocketbase`

**Solution:** Make the binary executable:

```bash
chmod +x pocketbase
```

### Task command not found

**Error:** `task: command not found` when running `task install-pocketbase`

**Solution:** Install Task runner or manually download PocketBase:

```bash
# Manual download (Linux amd64)
curl -L https://github.com/pocketbase/pocketbase/releases/download/v0.23.4/pocketbase_0.23.4_linux_amd64.zip -o pocketbase.zip
unzip pocketbase.zip
chmod +x pocketbase
rm pocketbase.zip
```
