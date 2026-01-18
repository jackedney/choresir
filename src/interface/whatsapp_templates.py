"""WhatsApp template message handling with 24-hour window detection.

WhatsApp Cloud API enforces a 24-hour messaging window. After a user's last message,
businesses can send freeform messages for 24 hours. Beyond that, only pre-approved
template messages can be sent.

This module provides utilities for:
1. Tracking the 24-hour messaging window
2. Sending template messages when outside the window
3. Documenting required templates to register in Twilio Console
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from twilio.base.exceptions import TwilioRestException

from src.core.config import constants, settings
from src.interface.whatsapp_sender import SendMessageResult, get_twilio_client


class MessageWindowTracker:
    """Tracks 24-hour messaging windows for WhatsApp users.

    WhatsApp allows freeform messages within 24 hours of a user's last message.
    This tracker helps determine if we need to use template messages.
    """

    def __init__(self) -> None:
        """Initialize message window tracker."""
        self._last_message_time: dict[str, datetime] = defaultdict(lambda: datetime.min)

    def record_user_message(self, phone: str) -> None:
        """Record when a user sent a message.

        Args:
            phone: User's phone number
        """
        self._last_message_time[phone] = datetime.now()

    def is_within_window(self, phone: str) -> bool:
        """Check if we're within the 24-hour messaging window for a user.

        Args:
            phone: User's phone number

        Returns:
            True if within 24-hour window, False if template required
        """
        last_message = self._last_message_time.get(phone, datetime.min)
        cutoff = datetime.now() - timedelta(hours=constants.WHATSAPP_MESSAGE_WINDOW_HOURS)
        return last_message > cutoff


# Global message window tracker (in-memory for MVP)
window_tracker = MessageWindowTracker()


async def send_template_message(
    *,
    to_phone: str,
    content_sid: str,
    variables: dict[str, str],
) -> SendMessageResult:
    """Send a WhatsApp template message using Twilio Content API.

    Template messages must be created in Twilio Console with Content API.
    Use this function when outside the 24-hour messaging window.

    Args:
        to_phone: Recipient phone number in E.164 format (e.g., "1234567890")
        content_sid: Twilio Content SID for the template (e.g., "HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        variables: Dictionary mapping variable positions to values (e.g., {"1": "chore_name", "2": "due_date"})

    Returns:
        SendMessageResult indicating success or failure
    """
    # Format phone number for Twilio WhatsApp
    to_whatsapp = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

    try:
        client = get_twilio_client()
        message = client.messages.create(
            from_=settings.twilio_whatsapp_number,
            to=to_whatsapp,
            content_sid=content_sid,
            content_variables=json.dumps(variables),
        )
        return SendMessageResult(success=True, message_id=message.sid)
    except TwilioRestException as e:
        return SendMessageResult(success=False, error=str(e))


"""
REQUIRED TEMPLATE MESSAGES TO CREATE IN TWILIO CONSOLE
=======================================================

You must create these templates in your Twilio Console using the Content API
before using them in production. After creation, add the Content SIDs to .env file.

Template: chore_reminder
Content Type: WhatsApp Template
Language: English (US)
Body Text:
  "🔔 Reminder: Your chore *{{1}}* is due {{2}}. Please complete it soon!"
Variables:
  {{1}} = Chore title (e.g., "Take out trash")
  {{2}} = Due date (e.g., "today at 5pm")
Config Setting: TEMPLATE_CHORE_REMINDER_SID
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      content_sid=settings.template_chore_reminder_sid,
      variables={"1": "Take out trash", "2": "today at 5pm"}
  )

---

Template: verification_request
Content Type: WhatsApp Template
Language: English (US)
Body Text:
  "{{1}} claims they completed *{{2}}*. Can you verify this?"
Variables:
  {{1}} = User name (e.g., "Alice")
  {{2}} = Chore title (e.g., "Dishes")
  {{3}} = Log ID (used in button payloads, not shown in body)
Buttons:
  - "✅ Approve" (quick_reply, payload: VERIFY:APPROVE:{{3}})
  - "❌ Reject" (quick_reply, payload: VERIFY:REJECT:{{3}})
Config Setting: TEMPLATE_VERIFICATION_REQUEST_SID
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      content_sid=settings.template_verification_request_sid,
      variables={"1": "Alice", "2": "Dishes", "3": "rec_abc123"}
  )

---

Template: conflict_notification
Content Type: WhatsApp Template
Language: English (US)
Body Text:
  "⚖️ There's a dispute about *{{1}}*. Your vote is needed to resolve it. Check your messages for details."
Variables:
  {{1}} = Chore title (e.g., "Vacuuming")
Config Setting: TEMPLATE_CONFLICT_NOTIFICATION_SID
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      content_sid=settings.template_conflict_notification_sid,
      variables={"1": "Vacuuming"}
  )

---

SETUP INSTRUCTIONS:
1. Go to Twilio Console (https://console.twilio.com/)
2. Navigate to Messaging > Content API > Create new content
3. Select "WhatsApp Template" as content type
4. For each template above:
   - Copy the body text exactly as shown
   - Configure variables using {{1}}, {{2}} format
   - Add buttons if specified
   - Submit for WhatsApp approval (usually takes 1-3 business days)
5. Once approved, copy the Content SID (format: HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)
6. Add to .env file:
   TEMPLATE_CHORE_REMINDER_SID=HXxxxx...
   TEMPLATE_VERIFICATION_REQUEST_SID=HXxxxx...
   TEMPLATE_CONFLICT_NOTIFICATION_SID=HXxxxx...
7. Templates can now be used via send_template_message()

NOTE: Content SIDs must be exact. Variable formatting ({{1}}, {{2}}) is required.
"""
