# Feature Request: Visual Proof & Media Handling

## Context
"A picture is worth a thousand words." When a user says "I cleaned the kitchen," the Verifier often has to walk to the kitchen to check. This defeats the purpose of remote management.

## User Story
As a user, I want to snap a photo of the clean sink and send it to the bot, so the Verifier can approve it from their bed/office/couch.

## Proposed Solution
Allow the bot to accept Image messages as a form of `tool_log_chore` trigger or attachment.

### Workflow
1. **User:** Sends a photo of the clean sink with caption "Done".
2. **Bot:**
   - Detects image.
   - Downloads/Buffers image temporarily (or gets public URL if possible via WhatsApp API).
   - Identifies the chore from the caption ("Done" + Context).
3. **Bot -> Verifier:**
   - Forwards the image to the Verifier.
   - Adds caption: "Alice claims she finished 'Clean Kitchen'. Proof attached. Verify?"
   - [ ✅ Approve ] [ ❌ Reject ]

## Technical Implementation
- **Update `whatsapp_parser.py`:** Currently, it likely ignores `image` type messages. It needs to extract the Image ID.
- **Media Handling:** Use WhatsApp Media API to retrieve the image URL.
- **Privacy/Storage:**
    - *Option A (Simple):* Do not store the image. Just grab the Media ID and re-send that Media ID to the Verifier. (WhatsApp allows re-sending media IDs for a limited time). This avoids hosting costs.
- **Agent Update:** The LLM (Claude 3.5 Sonnet) is multimodal. We can pass the image to the LLM to *auto-verify* simple things (e.g., "Is this sink empty?"), OR just pass the existence of the image as context to the human verifier.
    - *MVP:* Pass to human verifier. Do not overengineer AI vision yet.

## Acceptance Criteria
- [ ] Bot acknowledges receipt of images.
- [ ] When asking for verification, the bot forwards the user's image to the verifier.
- [ ] No permanent storage required (relay only).
