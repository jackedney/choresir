# ADR 009: Interactive Button-Based Verification

**Status:** Accepted  
**Date:** 2026-01-17

## Context

The original verification flow (ADR 003) required users to type text responses like "Yes", "Approve", or "No" to verify chore completion claims. This created unnecessary friction in the user experience:

- **Typing friction:** Users had to compose a text response, adding ~10 seconds to each verification
- **Ambiguity:** Variations like "Yeah sure", "ok", or typos required complex text parsing
- **Cognitive load:** Users needed to remember or look up the log ID for text-based commands

In household environments, quick actions are critical. Verification requests that require typing are often ignored or delayed, reducing accountability effectiveness.

## Decision

We will implement **WhatsApp Interactive Messages with Quick Reply Buttons** for all verification requests.

### Implementation Details

#### 1. Message Format

Verification requests now use Twilio's Content API templates with interactive buttons:

```text
{{1}} claims they completed *{{2}}*. Can you verify this?
[✅ Approve] [❌ Reject]
```

#### 2. Button Payload Structure

Button clicks send structured payloads that bypass the AI agent for deterministic, low-latency processing:

```text
Format: VERIFY:{DECISION}:{log_id}
Examples:
  - VERIFY:APPROVE:rec_abc123
  - VERIFY:REJECT:rec_abc123
```

#### 3. Processing Flow

1. **Webhook receives button click** with `ButtonPayload` parameter
2. **Parse payload** to extract decision and log_id
3. **Direct service call** to `verification_service.verify_chore()` (bypasses agent)
4. **Immediate confirmation** sent to user

#### 4. Fallback Support

Text-based verification remains supported for:

- Template approval delays during initial setup
- Users who prefer typing
- Edge cases where buttons don't render

Fallback format: `approve {log_id}` or `reject {log_id}`

### Technical Components

**Modified Files:**

- `src/interface/whatsapp_parser.py` - Detects button_reply message type
- `src/interface/webhook.py` - Routes button clicks to direct handler
- `src/services/notification_service.py` - Sends template messages with buttons
- `src/services/verification_service.py` - Processes verification decisions

**New Files:**

- `tests/unit/test_notification_service.py` - Comprehensive notification tests

### Template Configuration

Templates must be created in Twilio Console using Content API:

- **Template Name:** `verification_request`
- **Variables:** `{{1}}` = claimer name, `{{2}}` = chore title, `{{3}}` = log_id
- **Buttons:** Approve (payload: `VERIFY:APPROVE:{{3}}`), Reject (payload: `VERIFY:REJECT:{{3}}`)
- **Config:** `TEMPLATE_VERIFICATION_REQUEST_SID` in `.env`

## Consequences

### Positive

- **Reduced friction:** Interaction time drops from ~10s to <1s
- **Zero ambiguity:** Button clicks are deterministic, no text parsing needed
- **Better UX:** Tappable buttons feel native to WhatsApp
- **Lower latency:** Direct service calls bypass agent processing (~300ms saved)
- **Cost efficiency:** Fewer LLM calls for verification actions

### Negative

- **Template approval required:** Initial setup requires Twilio template approval (24-48 hours)
- **Template rigidity:** Button text and structure cannot be changed without re-approval
- **Payload size limits:** Button payloads limited to 256 characters (non-issue for current use)

### Mitigation

- Text-based fallback ensures system works during template approval
- Template variables allow personalization without re-approval
- Clear documentation in the Setup Guide for setup

## Related ADRs

- [ADR 003: Verification Protocol](003-verification.md) - Establishes verification requirement (this ADR improves the UX)
- [ADR 007: Operations](007-operations.md) - Operations and observability patterns used in implementation
- [ADR 019: Personal Chores](019-personal-chores.md) - Reuses interactive verification for personal chore verification
