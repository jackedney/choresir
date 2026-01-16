#!/bin/bash
set -e

echo "=== ngrok Static Domain Setup ==="
echo ""
echo "To get a static domain for your webhook, follow these steps:"
echo ""
echo "1. Go to https://dashboard.ngrok.com/domains"
echo "2. Click 'New Domain' or 'Create Domain'"
echo "3. Choose a subdomain (or use a random one)"
echo "4. Copy the domain name (e.g., 'your-subdomain.ngrok-free.app')"
echo ""
echo "Note: Free plan includes 1 static domain"
echo ""
read -p "Enter your static domain (or press Enter to skip): " STATIC_DOMAIN

if [ -z "$STATIC_DOMAIN" ]; then
    echo "Skipping static domain configuration."
    echo "ngrok will use a random URL each time."
    exit 0
fi

# Update ngrok.yml
echo "Updating ngrok.yml with static domain: $STATIC_DOMAIN"
cat > ngrok.yml <<EOF
region: us
version: '2'
authtoken: $(grep authtoken ~/.config/ngrok/ngrok.yml 2>/dev/null || grep authtoken ~/Library/Application\ Support/ngrok/ngrok.yml 2>/dev/null | awk '{print $2}')
tunnels:
  whatsapp-webhook:
    proto: http
    addr: 8000
    domain: $STATIC_DOMAIN
EOF

echo ""
echo "✅ Configuration updated!"
echo "Your webhook URL will be: https://$STATIC_DOMAIN"
echo ""
echo "Next steps:"
echo "1. Run 'task dev' to start the development environment"
echo "2. Configure Twilio webhook to: https://$STATIC_DOMAIN/webhook/whatsapp"
