"""Centralized message templates for WhatsApp notifications.

All user-facing message strings are defined here so domain vocabulary
can be changed in one place when the bot is repurposed.
"""


def verification_request(*, claimer_name: str, item_title: str, log_id: str) -> str:
    return (
        f"\u2705 {claimer_name} claims they completed *{item_title}*. "
        f"Can you verify this?\n\n"
        f"Reply 'approve {log_id}' to approve or 'reject {log_id}' to reject."
    )


def personal_verification_request(
    *,
    owner_name: str,
    item_title: str,
    log_id: str,
) -> str:
    return (
        f"\U0001f4aa Verification Request\n\n"
        f"{owner_name} claims they completed their personal task: '{item_title}'\n\n"
        f"Verify? Reply:\n"
        f"'/personal verify {log_id} approve' to approve\n"
        f"'/personal verify {log_id} reject' to reject"
    )


def deletion_request(*, requester_name: str, item_title: str) -> str:
    return (
        f"\U0001f5d1\ufe0f {requester_name} wants to remove *{item_title}*.\n\n"
        f"Reply 'approve deletion {item_title}' to approve or "
        f"'reject deletion {item_title}' to reject."
    )


def personal_verification_result(
    *,
    item_title: str,
    verifier_name: str,
    approved: bool,
    feedback: str = "",
) -> str:
    if approved:
        message = f"\u2705 Personal Task Verified\n\n{verifier_name} verified your '{item_title}'! Keep it up!"
    else:
        message = f"\u274c Personal Task Rejected\n\n{verifier_name} rejected your '{item_title}'."

    if feedback:
        message += f"\n\nFeedback: {feedback}"

    return message


def overdue_reminder(*, items: list[tuple[str, str]]) -> str:
    """Build overdue reminder message.

    Args:
        items: List of (title, deadline_date_str) tuples.
    """
    item_list = "\n".join([f"\u2022 {title} (due: {deadline})" for title, deadline in items])
    return (
        f"\U0001f514 Overdue Reminder\n\n"
        f"You have {len(items)} overdue task(s):\n\n"
        f"{item_list}\n\n"
        f"Please complete these as soon as possible."
    )


def daily_report(
    *,
    completions: int,
    overdue: int,
    pending_verifications: int,
    active_members: int,
) -> str:
    message = (
        f"\U0001f4ca Daily Report\n\n"
        f"Today's Summary:\n"
        f"\u2705 Completions: {completions}\n"
        f"\u23f0 Overdue: {overdue}\n"
        f"\u23f3 Pending Verification: {pending_verifications}\n\n"
        f"Active Members: {active_members}"
    )

    if overdue > 0 or pending_verifications > 0:
        message += "\n\nRemember to complete overdue tasks and verify pending ones!"

    return message


def personal_reminder(*, items: list[str]) -> str:
    item_list = "\n".join([f"\u2022 {title}" for title in items])
    return (
        f"\U0001f514 Personal Task Reminder\n\n"
        f"You have {len(items)} personal task(s) today:\n\n"
        f"{item_list}\n\n"
        f"Reply 'done [task]' when complete."
    )
