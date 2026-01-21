#!/bin/bash
set -e

# Load environment variables from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if required env vars are set
if [ -z "$POCKETBASE_ADMIN_EMAIL" ] || [ -z "$POCKETBASE_ADMIN_PASSWORD" ]; then
    echo "❌ Error: POCKETBASE_ADMIN_EMAIL and POCKETBASE_ADMIN_PASSWORD must be set in .env"
    exit 1
fi

# Stop any running PocketBase instances
pkill pocketbase 2>/dev/null || true
sleep 1

# Start PocketBase in background
echo "🚀 Starting PocketBase..."
./pocketbase serve > /tmp/pocketbase.log 2>&1 &
POCKETBASE_PID=$!

# Wait for PocketBase to be ready
echo "⏳ Waiting for PocketBase to start..."
for i in {1..10}; do
    if curl -s http://127.0.0.1:8090/api/health > /dev/null 2>&1; then
        echo "✅ PocketBase is running (PID: $POCKETBASE_PID)"
        break
    fi
    sleep 1
done

# Check if admin already exists by trying to auth
if curl -s -X POST http://127.0.0.1:8090/api/collections/_superusers/auth-with-password \
    -H "Content-Type: application/json" \
    -d "{\"identity\":\"$POCKETBASE_ADMIN_EMAIL\",\"password\":\"$POCKETBASE_ADMIN_PASSWORD\"}" \
    | grep -q "token"; then
    echo "✅ Admin account already exists and credentials are correct"
    echo "📊 PocketBase Admin UI: http://127.0.0.1:8090/_/"
    exit 0
fi

# Admin doesn't exist or wrong credentials - create it
echo "🔧 Creating admin account..."

# Use PocketBase's migrate command to create admin programmatically
pkill pocketbase 2>/dev/null || true
sleep 1

# Create admin using PocketBase superuser upsert command (creates or updates)
./pocketbase superuser upsert "$POCKETBASE_ADMIN_EMAIL" "$POCKETBASE_ADMIN_PASSWORD" > /tmp/admin_create.log 2>&1

# Start PocketBase again
echo "🚀 Restarting PocketBase with admin account..."
./pocketbase serve > /tmp/pocketbase.log 2>&1 &
POCKETBASE_PID=$!

# Wait for it to be ready
sleep 2
for i in {1..10}; do
    if curl -s http://127.0.0.1:8090/api/health > /dev/null 2>&1; then
        echo "✅ PocketBase is running with admin account (PID: $POCKETBASE_PID)"
        break
    fi
    sleep 1
done

# Verify admin login works
if curl -s -X POST http://127.0.0.1:8090/api/collections/_superusers/auth-with-password \
    -H "Content-Type: application/json" \
    -d "{\"identity\":\"$POCKETBASE_ADMIN_EMAIL\",\"password\":\"$POCKETBASE_ADMIN_PASSWORD\"}" \
    | grep -q "token"; then
    echo "✅ Admin authentication verified!"
    echo "📊 PocketBase Admin UI: http://127.0.0.1:8090/_/"
    echo "📧 Email: $POCKETBASE_ADMIN_EMAIL"
else
    echo "❌ Failed to verify admin authentication"
    exit 1
fi
