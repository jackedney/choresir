# WhatsApp Template Messages with Twilio Content API

This guide shows how to create, approve, and use WhatsApp message templates using Twilio's Content API.

## Overview

WhatsApp enforces a 24-hour messaging window. Template messages allow sending scheduled reminders and notifications outside this window. Twilio's Content API manages these templates and provides Content SIDs for use in your application.

**Approval time:** Usually 24-48 hours (can take up to 7 days)

---

## How to Create Templates in Twilio Console

### Step 1: Access Content Templates

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to **Messaging** → **Content Editor**
3. Click **"Create new Content"**

### Step 2: Configure Template Settings

1. **Content Type:** Select **"WhatsApp Template"**
2. **Language:** Choose your language (e.g., `en` for English)
3. **Template Name:** Use a descriptive name (e.g., `chore_reminder`, `verification_request`)
4. **Category:** Select **UTILITY** (not MARKETING or AUTHENTICATION)

### Step 3: Build Template Body

Use the visual editor or JSON mode:

**Variables:** Use `{{1}}`, `{{2}}`, `{{3}}` for dynamic content
- Variables must be numbered sequentially starting from 1
- Templates must end with text, not a variable

**Example:**
```
Hello {{1}}, this is a reminder about your chore: "{{2}}". The deadline is {{3}}. Please complete it on time.
```

### Step 4: Add Interactive Buttons (Optional)

For templates requiring user actions (like verification):

1. Click **"Add Buttons"** in the Content Editor
2. Choose **"Quick Reply"** type (NOT "Call to Action")
3. Configure each button:
   - **Button Text:** What users see (e.g., "✅ Approve")
   - **Button Payload:** Data sent to webhook (e.g., `VERIFY:APPROVE:{{3}}`)

**Note:** Button payloads can include variables!

### Step 5: Submit for Approval

1. Review the preview with example values
2. Click **"Submit for Approval"**
3. Wait for WhatsApp to approve (check Twilio Console for status)

---

## How to Find Content SIDs After Approval

Once WhatsApp approves your template:

### Method 1: Twilio Console

1. Go to **Messaging** → **Content Editor**
2. Find your approved template in the list
3. Click on the template name
4. Copy the **Content SID** (format: `HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

### Method 2: Twilio API

```bash
curl -X GET "https://content.twilio.com/v1/Content" \
  -u "TWILIO_ACCOUNT_SID:TWILIO_AUTH_TOKEN"
```

Look for your template name and copy the `sid` field.

### Store Content SIDs in Code

Update your configuration file with the Content SIDs:

```python
# src/interface/whatsapp_templates.py
TEMPLATE_CONTENT_SIDS = {
    "chore_reminder": "HXabcdef1234567890abcdef1234567890",
    "verification_request": "HXfedcba0987654321fedcba0987654321",
    "household_update": "HX1122334455667788991122334455667788",
    "conflict_notification": "HX9988776655443322119988776655443322",
}
```

---

## How to Test Templates

### Test via Twilio Console

1. Go to **Messaging** → **Content Editor**
2. Click on your approved template
3. Click **"Send Test Message"**
4. Enter:
   - **To Phone Number:** Your WhatsApp number (must be registered)
   - **From Number:** Your Twilio WhatsApp sender (e.g., `whatsapp:+14155238886`)
   - **Variable Values:** Fill in example data for `{{1}}`, `{{2}}`, etc.
5. Click **"Send"**
6. Check your WhatsApp to verify receipt and appearance

### Test via Code

```python
from twilio.rest import Client

client = Client(account_sid, auth_token)

# Send template message
message = client.messages.create(
    from_='whatsapp:+14155238886',
    content_sid='HXabcdef1234567890abcdef1234567890',  # Your Content SID
    content_variables={
        "1": "Alice",
        "2": "Wash Dishes",
        "3": "Jan 16, 8:00 PM"
    },
    to='whatsapp:+1234567890'
)

print(f"Message sent: {message.sid}")
```

### Test Interactive Buttons

For templates with Quick Reply buttons:

1. Send a test message (via Console or code)
2. Tap each button in WhatsApp
3. Verify your webhook receives the correct payload
4. Check webhook logs in Twilio Console:
   - Go to **Monitor** → **Logs** → **Webhook Logs**
   - Confirm `ButtonPayload` matches expected format

---

## Template Specifications

### 1. Chore Reminder

**Purpose:** Remind users about upcoming chore deadlines

**Template Name:** `chore_reminder`
**Category:** UTILITY
**Content SID:** `HXabcdef1234567890abcdef1234567890` *(replace after approval)*

**Body:**
```
Hello {{1}}, this is a reminder about your chore: "{{2}}". The deadline is {{3}}. Please complete it on time.
```

**Variables:**
- `{{1}}` - User's display name
- `{{2}}` - Chore title
- `{{3}}` - Formatted deadline (e.g., "Jan 16, 8:00 PM")

**Example Message:**
```
Hello Alice, this is a reminder about your chore: "Wash Dishes". The deadline is Jan 16, 8:00 PM. Please complete it on time.
```

**Usage in Code:**
```python
send_template_message(
    phone_number="+1234567890",
    content_sid=TEMPLATE_CONTENT_SIDS["chore_reminder"],
    variables={
        "1": user.display_name,
        "2": chore.title,
        "3": formatted_deadline
    }
)
```

---

### 2. Verification Request (Interactive)

**Purpose:** Request verification of completed chores with approve/reject buttons

**Template Name:** `verification_request`
**Category:** UTILITY
**Content SID:** `HXfedcba0987654321fedcba0987654321` *(replace after approval)*

**Body:**
```
{{1}} claims they completed *{{2}}*. Can you verify this?
```

**Variables:**
- `{{1}}` - Name of user who claimed completion
- `{{2}}` - Chore title (markdown formatting supported)
- `{{3}}` - Log ID (used in button payloads, not shown in body)

**Buttons (Quick Reply type):**
1. **Approve Button**
   - Text: `✅ Approve`
   - Payload: `VERIFY:APPROVE:{{3}}`

2. **Reject Button**
   - Text: `❌ Reject`
   - Payload: `VERIFY:REJECT:{{3}}`

**Example Message:**
```
Alice claims they completed *Wash Dishes*. Can you verify this?
[✅ Approve] [❌ Reject]
```

**Implementation Notes:**
- Buttons send payloads directly to webhook (no AI processing needed)
- Fallback: Users can still type `approve {log_id}` or `reject {log_id}`
- Button payloads are deterministic and faster than text parsing
- See ADR 005 for architecture details

**Usage in Code:**
```python
send_template_message(
    phone_number=verifier_phone,
    content_sid=TEMPLATE_CONTENT_SIDS["verification_request"],
    variables={
        "1": completer.name,
        "2": chore.title,
        "3": str(log.id)  # Used in button payload
    }
)
```

---

### 3. Household Update Notification

**Purpose:** Notify household members about changes (new members, removed members, settings)

**Template Name:** `household_update`
**Category:** UTILITY
**Content SID:** `HX1122334455667788991122334455667788` *(replace after approval)*

**Body:**
```
Household update: {{1}}. This change was made by {{2}}.
```

**Variables:**
- `{{1}}` - Description of the change (e.g., "Alice was added to the household")
- `{{2}}` - Name of person who made the change

**Example Message:**
```
Household update: Alice was added to the household. This change was made by Bob.
```

**Usage in Code:**
```python
send_template_message(
    phone_number=member_phone,
    content_sid=TEMPLATE_CONTENT_SIDS["household_update"],
    variables={
        "1": update_description,
        "2": admin.name
    }
)
```

---

### 4. Conflict Notification

**Purpose:** Alert household members when a chore verification is disputed

**Template Name:** `conflict_notification`
**Category:** UTILITY
**Content SID:** `HX9988776655443322119988776655443322` *(replace after approval)*

**Body:**
```
A chore completion is in conflict: "{{1}}". Your vote is needed to resolve this dispute. Reply to this message to vote.
```

**Variables:**
- `{{1}}` - Chore title

**Example Message:**
```
A chore completion is in conflict: "Clean Kitchen". Your vote is needed to resolve this dispute. Reply to this message to vote.
```

**Usage in Code:**
```python
send_template_message(
    phone_number=member_phone,
    content_sid=TEMPLATE_CONTENT_SIDS["conflict_notification"],
    variables={
        "1": chore.title
    }
)
```

---

## Template Submission Checklist

Before submitting each template for approval:

- [ ] Template name is descriptive and matches code reference (e.g., `chore_reminder`)
- [ ] Category is **UTILITY** (not MARKETING or AUTHENTICATION)
- [ ] Language is correctly selected (e.g., `en` for English)
- [ ] Variables are numbered sequentially: `{{1}}`, `{{2}}`, `{{3}}`
- [ ] Template body ends with text, not a variable
- [ ] Preview shows realistic example values
- [ ] **For interactive templates:**
  - [ ] Buttons are **Quick Reply** type (NOT "Call to Action")
  - [ ] Button text is clear and concise (max 20 characters)
  - [ ] Button payloads use correct format (e.g., `VERIFY:APPROVE:{{3}}`)
  - [ ] Payload includes variable for tracking (like log ID)

---

## Common Rejection Reasons & Fixes

| Rejection Reason | Solution |
|------------------|----------|
| "Violates marketing policy" | Ensure category is **UTILITY**, not MARKETING |
| "Template ends with variable" | Add closing text after the last variable |
| "Variable formatting incorrect" | Use `{{1}}` format, not `{1}`, `$1`, or `%s` |
| "Contains prohibited content" | Remove URLs, promotional language, excessive emojis |
| "Button configuration invalid" | Use Quick Reply type and ensure payload format is correct |
| "Missing required fields" | Check that language and category are set |

---

## After Approval Workflow

### 1. Retrieve Content SIDs

Once approved, get the Content SIDs from Twilio Console or API (see "How to Find Content SIDs" above).

### 2. Update Code Configuration

Add Content SIDs to your configuration:

```python
# src/interface/whatsapp_templates.py
TEMPLATE_CONTENT_SIDS = {
    "chore_reminder": "HXabcdef1234567890abcdef1234567890",
    "verification_request": "HXfedcba0987654321fedcba0987654321",
    "household_update": "HX1122334455667788991122334455667788",
    "conflict_notification": "HX9988776655443322119988776655443322",
}
```

### 3. Test Templates

Test each template using the methods described in "How to Test Templates" section.

### 4. Deploy to Production

Once all templates are tested and working:

1. Update environment variables with Content SIDs
2. Deploy code changes
3. Monitor webhook logs for any errors
4. Verify production messages are received correctly

---

## FAQ

### Can I edit templates after approval?

No. You must submit a new version and wait for re-approval. The old template will continue to work until you switch to the new Content SID.

### Do templates cost money?

Twilio charges per conversation. First 1,000 conversations/month may be free depending on your plan. After that, approximately $0.005-$0.02 per conversation.

### What if my template is rejected?

1. Check rejection reason in Twilio Console
2. Fix the issue based on common rejection reasons (see table above)
3. Resubmit the template
4. Wait for re-approval

### How many variables can a template have?

WhatsApp supports up to 10 variables per template body. Button payloads can also contain variables.

### What's the difference between Quick Reply and Call to Action buttons?

- **Quick Reply:** Sends a payload to your webhook when clicked (used for in-app actions like Approve/Reject)
- **Call to Action:** Opens a URL or phone number (used for external actions)
- Use **Quick Reply** for verification buttons and similar interactions

### Can button payloads contain variables?

Yes! Use `{{variable_number}}` in button payloads.

**Example:** `VERIFY:APPROVE:{{3}}` where `{{3}}` is the log ID

When sending, Twilio will replace `{{3}}` with the actual value:
```python
variables={"3": "12345"}  # Becomes payload: VERIFY:APPROVE:12345
```

### How do I handle button responses in my webhook?

When a user clicks a button, Twilio sends a webhook with:

```json
{
  "ButtonPayload": "VERIFY:APPROVE:12345",
  "From": "whatsapp:+1234567890",
  "Body": ""
}
```

Parse the `ButtonPayload` field to determine the action:

```python
def handle_webhook(request):
    payload = request.form.get("ButtonPayload")
    if payload:
        # Button was clicked
        action, decision, log_id = payload.split(":")
        if action == "VERIFY":
            process_verification(decision, log_id)
    else:
        # Regular text message
        body = request.form.get("Body")
        process_text_message(body)
```

### How long do templates stay approved?

Templates remain approved indefinitely unless:
- WhatsApp policy changes require re-approval
- Your template is reported for abuse
- You delete and recreate the template

### Can I use the same template name in different languages?

Yes! Create separate templates for each language with the same name:
- `chore_reminder` (English)
- `chore_reminder` (Spanish)
- `chore_reminder` (French)

Each will have a different Content SID. Select the appropriate SID based on user's language preference.

---

## Timeline Estimate

| Task | Estimated Time |
|------|----------------|
| Create 4 templates in Twilio Console | 30-45 minutes |
| WhatsApp approval wait | 24-48 hours |
| Retrieve Content SIDs | 5 minutes |
| Update code configuration | 10 minutes |
| Test all templates | 20 minutes |
| Deploy to production | 15 minutes |
| **Total** | **~2-3 days** (mostly waiting for approval) |

---

## Troubleshooting

### Template not sending

1. Check Content SID is correct in code
2. Verify template is approved in Twilio Console
3. Check phone number format (must include `whatsapp:` prefix)
4. Review error logs in Twilio Console under **Monitor** → **Logs**

### Button payloads not working

1. Verify buttons are **Quick Reply** type (not Call to Action)
2. Check webhook is configured to receive `ButtonPayload` parameter
3. Test payload format matches expected structure
4. Review webhook logs for received payloads

### Variables not substituting

1. Ensure variable names in code match template variables (`"1"`, `"2"`, `"3"`)
2. Check all required variables are provided
3. Verify Content SID matches the template you're testing

### Template rejected repeatedly

1. Read rejection message carefully
2. Compare against WhatsApp's template guidelines
3. Simplify template (remove emojis, formatting, URLs)
4. Contact Twilio support if rejection reason is unclear

---

## Resources

- [Twilio Content API Documentation](https://www.twilio.com/docs/content-api)
- [WhatsApp Template Message Guidelines](https://developers.facebook.com/docs/whatsapp/message-templates/guidelines)
- [Twilio Console - Content Editor](https://console.twilio.com/us1/develop/sms/content-editor)
- [Twilio Webhook Logs](https://console.twilio.com/us1/monitor/logs/webhooks)
