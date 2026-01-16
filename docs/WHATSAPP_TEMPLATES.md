# WhatsApp Template Messages Setup

Meta WhatsApp enforces a 24-hour messaging window. Template messages allow sending scheduled reminders and notifications outside this window.

**Approval time:** 24-48 hours (up to 7 days)

## Required Templates

### 1. Chore Reminder

**Name:** `chore_reminder`
**Category:** UTILITY
**Body:**
```
Hello {{1}}, this is a reminder about your chore: "{{2}}". The deadline is {{3}}. Please complete it on time.
```

**Variables:**
1. User's display name
2. Chore title
3. Formatted deadline

**Example:**
```
Hello Alice, this is a reminder about your chore: "Wash Dishes". The deadline is Jan 16, 8:00 PM. Please complete it on time.
```

### 2. Verification Request

**Name:** `verification_request`
**Category:** UTILITY
**Body:**
```
{{1}} has completed: "{{2}}". Please verify or reject this completion. Reply to this message to respond.
```

**Variables:**
1. User who completed the chore
2. Chore title

**Example:**
```
Bob has completed: "Mow Lawn". Please verify or reject this completion. Reply to this message to respond.
```

### 3. Conflict Notification

**Name:** `conflict_notification`
**Category:** UTILITY
**Body:**
```
A chore completion is in conflict: "{{1}}". Your vote is needed to resolve this dispute. Reply to this message to vote.
```

**Variables:**
1. Chore title

**Example:**
```
A chore completion is in conflict: "Clean Kitchen". Your vote is needed to resolve this dispute. Reply to this message to vote.
```

## Submission Process

1. Go to [Meta Developer Console](https://developers.facebook.com)
2. Navigate to **WhatsApp** → **Message Templates**
3. Click **"Create Template"**
4. Submit each template using details above
5. Wait for approval email

## Submission Checklist

For each template:
- [ ] Template name matches exactly (e.g., `chore_reminder`)
- [ ] Category is **UTILITY** (not MARKETING)
- [ ] Language is correct
- [ ] Variables are formatted as `{{1}}`, `{{2}}`, etc.
- [ ] Template ends with text (not a variable)
- [ ] Example preview makes sense

## Common Rejection Reasons

| Reason | Fix |
|--------|-----|
| "Violates marketing policy" | Ensure category is UTILITY |
| "Template ends with variable" | Add closing text after last variable |
| "Variable formatting incorrect" | Use `{{1}}` not `{1}` or `$1` |
| "Contains prohibited content" | Remove URLs, promotional language, emojis |

## After Approval

1. Note the **Template ID** from Meta console (e.g., `chore_reminder_12345_en`)
2. Update `src/interface/whatsapp_templates.py`:
```python
TEMPLATE_IDS = {
    "chore_reminder": "chore_reminder_12345_en",
    "verification_request": "verification_request_67890_en",
    "conflict_notification": "conflict_notification_11223_en",
}
```

## Testing

**Via Meta Console:**
1. Go to **Message Templates**
2. Click approved template
3. **"Send Test Message"**
4. Verify receipt on WhatsApp

**Via Code:**
```python
result = send_template_message(
    phone_number="+1234567890",
    template_name="chore_reminder",
    variables=["Alice", "Wash Dishes", "Jan 16, 8:00 PM"]
)
```

## FAQ

**Can I edit templates after approval?**
No. Submit a new version and wait for re-approval.

**Do templates cost money?**
First 1,000 conversations/month are free. After that, ~$0.005-0.02 per conversation.

**What if my template is rejected?**
Read rejection reason and resubmit with fixes.

**How many variables can a template have?**
Up to 10 variables per template.

## Timeline

| Task | Time |
|------|------|
| Submit 3 templates | 15-30 minutes |
| Meta approval | 24-48 hours |
| Test templates | 10 minutes |
| Update code | 5 minutes |
| **Total** | **1-3 days** |
