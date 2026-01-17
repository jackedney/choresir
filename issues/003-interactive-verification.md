# Feature Request: Low-Friction Verification via WhatsApp Buttons

## Context
Currently, verification requires a user to type a reply ("Yes", "Approve", "No"). This adds friction. In a busy household, users ignore text-based requests that require typing.

## User Story
As a verifier, I want to tap a single button to approve a chore so that I can get back to my life immediately.

## Proposed Solution
Utilize WhatsApp **Interactive Messages** (Quick Reply Buttons) for all verification requests.

### Current Flow
> **Bot:** "Alice claimed she did the dishes. Verify?"
> **User:** (Types) "Yes"

### New Flow
> **Bot:** "Alice claimed she did the dishes. Verify?"
> [ ✅ Approve ] [ ❌ Reject ]

**UX Benefits:**
- Reduces interaction time from ~10s to <1s.
- Removes ambiguity (no more "Yeah sure" or typo handling).

## Technical Implementation
- **Update `whatsapp_sender.py`:** Add support for `type="interactive"` messages in the API payload.
- **Update `whatsapp_parser.py`:** Handle `interactive` webhook events (button clicks return a specific payload ID, not just text body).
- **Agent Logic:** The agent currently processes text. We need a middleware or logic in the parser to translate Button Payloads (e.g., `PAYLOAD_VERIFY_LOG_123_APPROVE`) into a natural language equivalent for the agent, OR bypass the agent LLM entirely for these deterministic actions to save latency and cost.
    - *Suggestion:* Translate payload to text "System: User clicked Approve on Log 123" and feed that to the agent.

## Acceptance Criteria
- [ ] Verification requests send a message with two buttons: Approve / Reject.
- [ ] Clicking a button triggers the appropriate `tool_verify_chore` action.
- [ ] Fallback to text input is still supported.
