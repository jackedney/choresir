#!/bin/bash
# Start ngrok tunnel for local webhook testing

set -e

PORT=${1:-8000}

echo "Starting ngrok tunnel on port $PORT..."
echo ""
echo "After ngrok starts:"
echo "1. Copy the HTTPS forwarding URL (e.g., https://abc123.ngrok.io)"
echo "2. Go to Meta Developer Console > WhatsApp > Configuration"
echo "3. Update webhook URL to: <ngrok-url>/webhook"
echo "4. Update verify token to match WHATSAPP_VERIFY_TOKEN in .env"
echo ""

ngrok http $PORT
