# PocketBase Setup

## Automatic Setup (Recommended)

The easiest way to set up PocketBase is to use the integrated dev command:

```bash
task dev
```

This will automatically:
- Download and install PocketBase (if not present)
- Start the PocketBase server
- Create the admin account with default credentials
- Start all other services (FastAPI and ngrok)

**Default Admin Credentials:**
- Email: `admin@test.local`
- Password: `testpassword123`

These credentials are used by the application for schema synchronization.

## Manual Setup

If you prefer manual setup:

### 1. Install PocketBase

```bash
task install-pocketbase
```

This downloads PocketBase v0.23.4 for your platform.

### 2. Start PocketBase

```bash
./pocketbase serve
```

### 3. Create Admin Account

**Option A: Via CLI (Recommended)**
```bash
./pocketbase superuser upsert admin@test.local testpassword123
```

**Option B: Via Browser**
1. Open http://127.0.0.1:8090/_/
2. Create a superuser account
3. Use the credentials: `admin@test.local` / `testpassword123`

## Server Information
- **URL:** http://127.0.0.1:8090
- **REST API:** http://127.0.0.1:8090/api/
- **Admin Dashboard:** http://127.0.0.1:8090/_/

## Managing PocketBase

### Start Server
```bash
./pocketbase serve
```

### Stop Server
```bash
# Find PID and kill
cat pocketbase.pid | xargs kill
```

### Check if Running
```bash
curl -s http://127.0.0.1:8090/api/health
```

## Data Storage
PocketBase stores all data in the `pb_data/` directory (already in .gitignore).

## Environment Configuration
After creating your admin account, add the PocketBase URL to your `.env` file:
```
POCKETBASE_URL=http://127.0.0.1:8090
```
