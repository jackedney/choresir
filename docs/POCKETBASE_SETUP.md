# PocketBase Setup

## Current Status
PocketBase v0.35.1 is downloaded and running locally.

## Server Information
- **URL:** http://127.0.0.1:8090
- **REST API:** http://127.0.0.1:8090/api/
- **Admin Dashboard:** http://127.0.0.1:8090/_/

## Creating Your Admin Account

**IMPORTANT:** You must create an admin account before using the application.

1. Open the admin dashboard URL in your browser:
   http://127.0.0.1:8090/_/

2. On first launch, you'll be prompted to create a superuser account
3. Choose a secure email and password
4. Save these credentials - you'll need them to access the admin panel

## Alternative: CLI Admin Creation
You can also create a superuser via command line:
```bash
./pocketbase superuser upsert admin@example.com YourSecurePassword
```

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
