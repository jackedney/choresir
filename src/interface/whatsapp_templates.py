"""WhatsApp template message handling with 24-hour window detection.

WhatsApp Cloud API enforces a 24-hour messaging window. After a user's last message,
businesses can send freeform messages for 24 hours. Beyond that, only pre-approved
template messages can be sent.

This module provides utilities for:
1. Tracking the 24-hour messaging window
2. Sending template messages when outside the window
3. Documenting required templates to register in Meta Developer Console
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.core.config import constants, settings


class TemplateMessageResult(BaseModel):
    """Result of sending a WhatsApp template message."""

    success: bool = Field(..., description="Whether the template was sent successfully")
    message_id: str | None = Field(None, description="WhatsApp message ID if successful")
    error: str | None = Field(None, description="Error message if failed")


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
    template_name: str,
    template_params: list[str] | None = None,
    language_code: str = "en_US",
) -> TemplateMessageResult:
    """Send a WhatsApp template message.

    Template messages must be pre-approved in Meta Developer Console.
    Use this function when outside the 24-hour messaging window.

    Args:
        to_phone: Recipient phone number in E.164 format
        template_name: Name of the approved template (e.g., "chore_reminder")
        template_params: List of parameter values for template variables
        language_code: Template language code (default: en_US)

    Returns:
        TemplateMessageResult indicating success or failure
    """
    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    # Build template components
    components = []
    if template_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in template_params],
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=constants.API_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == constants.HTTP_OK:
                data: dict[str, Any] = response.json()
                message_id = data.get("messages", [{}])[0].get("id")

                return TemplateMessageResult(
                    success=True,
                    message_id=message_id,
                )

            error_data = response.json() if response.text else {}
            error_message = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")

            return TemplateMessageResult(
                success=False,
                error=f"Template send failed: {error_message}",
            )

    except Exception as e:
        return TemplateMessageResult(
            success=False,
            error=f"Unexpected error: {e!s}",
        )


"""
REQUIRED TEMPLATE MESSAGES TO REGISTER IN META DEVELOPER CONSOLE
==================================================================

You must create and get approval for these templates in your Meta Developer Console
(WhatsApp > Message Templates section) before using them in production.

Template Name: chore_reminder
Category: UTILITY
Language: English (US)
Body Text:
  "🔔 Reminder: Your chore *{{1}}* is due {{2}}. Please complete it soon!"
Variables:
  {{1}} = Chore title (e.g., "Take out trash")
  {{2}} = Due date (e.g., "today at 5pm")
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      template_name="chore_reminder",
      template_params=["Take out trash", "today at 5pm"]
  )

---

Template Name: verification_request
Category: UTILITY
Language: English (US)
Body Text:
  "✅ {{1}} claims they completed *{{2}}*. Can you verify this?"
Variables:
  {{1}} = User name (e.g., "Alice")
  {{2}} = Chore title (e.g., "Dishes")
Buttons:
  - "Yes, verified" (quick_reply)
  - "No, not done" (quick_reply)
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      template_name="verification_request",
      template_params=["Alice", "Dishes"]
  )

---

Template Name: conflict_notification
Category: UTILITY
Language: English (US)
Body Text:
  "⚖️ There's a dispute about *{{1}}*. Your vote is needed to resolve it. Check your messages for details."
Variables:
  {{1}} = Chore title (e.g., "Vacuuming")
Example Usage:
  await send_template_message(
      to_phone="1234567890",
      template_name="conflict_notification",
      template_params=["Vacuuming"]
  )

---

SETUP INSTRUCTIONS:
1. Go to Meta Developers (https://developers.facebook.com/)
2. Navigate to your WhatsApp Business App
3. Go to WhatsApp > Message Templates
4. Click "Create Template" for each template above
5. Copy the body text exactly as shown
6. Submit for approval (usually takes 1-3 business days)
7. Once approved, templates can be used via send_template_message()

NOTE: Template names must match exactly. Variable formatting ({{1}}, {{2}}) is required.
"""
