# ngrok Static Domain Setup

## Why Use a Static Domain?

By default, ngrok generates a random URL each time it starts (e.g., `https://abc-xyz-123.ngrok-free.app`). This means you would need to update your Twilio webhook URL every time you restart your development environment.

A **static domain** stays the same across restarts, so you only need to configure Twilio once.

## Setup Instructions

### Option 1: Automatic Setup (Recommended)

Run the setup task:

```bash
task setup-ngrok
```

This will:
1. Guide you to create a static domain on the ngrok dashboard
2. Save the domain to `.ngrok-domain` file
3. Configure `task dev` to use this domain automatically

### Option 2: Manual Setup

1. **Visit ngrok dashboard:**
   ```
   https://dashboard.ngrok.com/domains
   ```

2. **Create a domain:**
   - Click "Create Domain" or "New Domain"
   - Free plan includes 1 static domain
   - Copy the domain name (e.g., `your-app-name.ngrok-free.app`)

3. **Save the domain:**
   ```bash
   echo "your-app-name.ngrok-free.app" > .ngrok-domain
   ```

4. **Start development:**
   ```bash
   task dev
   ```

   ngrok will now use your static domain!

## Verify Configuration

After setup, when you run `task dev`, you should see:

```
Starting ngrok...
Using saved static domain: your-app-name.ngrok-free.app
Webhook URL: https://your-app-name.ngrok-free.app/webhook/whatsapp
```

## Configure Twilio Webhook

Once you have your static domain, configure Twilio to send WhatsApp messages to:

```
https://your-app-name.ngrok-free.app/webhook/whatsapp
```

This URL will remain the same across all development sessions.

## Troubleshooting

### Domain already in use

If you see an error like "endpoint is already online", another ngrok instance is using this domain. Stop it with:

```bash
task stop-dev
# or
pkill ngrok
```

### Lost domain

If you forgot your domain, check:

```bash
cat .ngrok-domain
```

Or visit: https://dashboard.ngrok.com/domains

### Using random domain

If `.ngrok-domain` is empty or missing, `task dev` will use a random domain. You'll see:

```
Using random domain for now...
```

Run `task setup-ngrok` to configure a static domain.
