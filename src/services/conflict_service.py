"""Conflict resolution service for voting on disputed chores."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.domain.chore import ChoreState
from src.domain.user import UserStatus
from src.services import chore_state_machine


logger = logging.getLogger(__name__)


class VoteChoice(StrEnum):
    """Vote choice enum."""

    YES = "YES"  # Approve the completion claim
    NO = "NO"  # Reject the completion claim


class VoteResult(StrEnum):
    """Vote tally result enum."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEADLOCK = "DEADLOCK"


async def initiate_vote(*, chore_id: str) -> list[dict[str, Any]]:
    """Initiate voting process for a conflict.

    Creates vote records for all eligible members (excludes claimer and rejecter).
    Sends notifications to eligible voters.

    Args:
        chore_id: Chore ID in CONFLICT state

    Returns:
        List of created vote placeholder records

    Raises:
        ValueError: If chore is not in CONFLICT state
        db_client.RecordNotFoundError: If chore not found
    """
    # Guard: Verify chore is in CONFLICT state
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.CONFLICT:
        msg = f"Cannot initiate vote: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Get claimer and rejecter from logs
    # Note: PocketBase has issues with filtering on relation fields, so get all logs and filter in Python
    all_logs = await db_client.list_records(
        collection="logs",
        filter_query="",
        per_page=500,
        sort="",
    )

    # Filter for this chore's claimed_completion and reject_verification logs
    logs = [
        log
        for log in all_logs
        if log.get("chore_id") == chore_id and log.get("action") in ["claimed_completion", "reject_verification"]
    ]

    excluded_user_ids = {log["user_id"] for log in logs}

    # Get all active users
    all_users = await db_client.list_records(
        collection="users",
        filter_query=f'status = "{UserStatus.ACTIVE}"',
    )

    # Filter out excluded users
    eligible_voters = [u for u in all_users if u["id"] not in excluded_user_ids]

    logger.info(
        "Initiating vote for chore %s with %d eligible voters (excluded: %s)",
        chore_id,
        len(eligible_voters),
        excluded_user_ids,
    )

    # Create vote placeholder logs (will be updated when votes are cast)
    vote_records = []
    for voter in eligible_voters:
        vote_log = {
            "chore_id": chore_id,
            "user_id": voter["id"],
            "action": "vote_pending",
            "timestamp": datetime.now().isoformat(),
        }
        record = await db_client.create_record(collection="logs", data=vote_log)
        vote_records.append(record)

    # Note: Voter notification system not yet implemented

    return vote_records


async def cast_vote(
    *,
    chore_id: str,
    voter_user_id: str,
    choice: VoteChoice,
) -> dict[str, Any]:
    """Cast a vote on a conflict.

    Records the vote and checks if all votes are in.

    Args:
        chore_id: Chore ID in CONFLICT state
        voter_user_id: ID of user casting vote
        choice: YES or NO

    Returns:
        Updated vote log record

    Raises:
        DuplicateVoteError: If user already voted
        ValueError: If chore is not in CONFLICT state
        db_client.RecordNotFoundError: If vote placeholder not found
    """
    # Guard: Verify chore is in CONFLICT state
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.CONFLICT:
        msg = f"Cannot cast vote: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Get all logs and filter in Python (PocketBase has issues with relation field filtering)
    all_logs = await db_client.list_records(
        collection="logs",
        filter_query="",
        per_page=500,
        sort="",  # No sort to avoid issues
    )

    # Guard: Check if user already voted
    existing_votes = [
        log
        for log in all_logs
        if log.get("chore_id") == chore_id
        and log.get("user_id") == voter_user_id
        and log.get("action") in ["vote_yes", "vote_no"]
    ]
    if existing_votes:
        msg = f"User {voter_user_id} already voted on chore {chore_id}"
        raise ValueError(msg)

    # Find the pending vote record
    pending_votes = [
        log
        for log in all_logs
        if log.get("chore_id") == chore_id
        and log.get("user_id") == voter_user_id
        and log.get("action") == "vote_pending"
    ]

    if not pending_votes:
        msg = f"No pending vote found for user {voter_user_id} on chore {chore_id}"
        raise db_client.RecordNotFoundError(msg)

    pending_vote = pending_votes[0]

    # Update vote record
    vote_action = f"vote_{choice.lower()}"
    updated_vote = await db_client.update_record(
        collection="logs",
        record_id=pending_vote["id"],
        data={
            "action": vote_action,
            "timestamp": datetime.now().isoformat(),
        },
    )

    logger.info("User %s voted %s on chore %s", voter_user_id, choice, chore_id)

    # Check if all votes are in
    # Note: PocketBase has issues with filtering on relation fields, so get all logs and filter in Python
    all_logs = await db_client.list_records(
        collection="logs",
        filter_query="",  # Get all logs
        per_page=500,  # Increase page size to avoid pagination issues
        sort="",  # No sort to avoid issues
    )

    # Filter manually for vote_pending logs for this chore
    pending_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_pending"]

    if not pending_votes:
        logger.info("All votes received for chore %s, ready to tally", chore_id)
        # Note: Automatic tally triggering not yet implemented

    return updated_vote


async def tally_votes(*, chore_id: str) -> tuple[VoteResult, dict[str, Any]]:
    """Tally votes and resolve the conflict.

    Voting rules:
    - Odd population: majority wins
    - Even population: check for deadlock (tie)
    - Deadlock: chore transitions to DEADLOCK state

    Args:
        chore_id: Chore ID in CONFLICT state

    Returns:
        Tuple of (result, updated_chore_record)

    Raises:
        ValueError: If chore is not in CONFLICT state
        ConflictServiceError: If not all votes are cast yet
    """
    # Guard: Verify chore is in CONFLICT state
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.CONFLICT:
        msg = f"Cannot tally votes: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Get all logs and filter in Python (PocketBase has issues with relation field filtering)
    all_logs = await db_client.list_records(
        collection="logs",
        filter_query="",
        per_page=500,
        sort="",  # No sort to avoid issues
    )

    # Filter votes for this chore
    pending_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_pending"]

    # Guard: Verify all votes are cast
    if pending_votes:
        msg = f"Cannot tally: {len(pending_votes)} votes still pending for chore {chore_id}"
        raise ValueError(msg)

    # Get all votes
    yes_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_yes"]
    no_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_no"]

    yes_count = len(yes_votes)
    no_count = len(no_votes)
    total_votes = yes_count + no_count

    logger.info(
        "Tallying votes for chore %s: %d yes, %d no (total: %d)",
        chore_id,
        yes_count,
        no_count,
        total_votes,
    )

    # Determine result
    if yes_count > no_count:
        result = VoteResult.APPROVED
        # Complete the chore
        updated_chore = await chore_state_machine.transition_to_completed(chore_id=chore_id)
        logger.info("Vote result: APPROVED - chore %s completed", chore_id)

    elif no_count > yes_count:
        result = VoteResult.REJECTED
        # Reset chore to TODO
        updated_chore = await chore_state_machine.transition_to_todo(chore_id=chore_id)
        logger.info("Vote result: REJECTED - chore %s reset to TODO", chore_id)

    else:  # Tie - deadlock
        result = VoteResult.DEADLOCK
        # Transition to DEADLOCK state
        updated_chore = await chore_state_machine.transition_to_deadlock(chore_id=chore_id)
        logger.warning("Vote result: DEADLOCK - chore %s in deadlock state", chore_id)

    # Create tally log
    tally_log = {
        "chore_id": chore_id,
        "user_id": None,  # System action (no user)
        "action": f"vote_tally: {result.lower()} (yes: {yes_count}, no: {no_count})",
        "timestamp": datetime.now().isoformat(),
    }
    await db_client.create_record(collection="logs", data=tally_log)

    return result, updated_chore


async def get_vote_status(*, chore_id: str) -> dict[str, Any]:
    """Get voting status for a chore.

    Args:
        chore_id: Chore ID

    Returns:
        Dictionary with vote counts and status
    """
    # Get all logs and filter in Python (PocketBase has issues with relation field filtering)
    all_logs = await db_client.list_records(
        collection="logs",
        filter_query="",
        per_page=500,
        sort="",  # No sort to avoid issues
    )

    # Filter votes for this chore
    yes_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_yes"]
    no_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_no"]
    pending_votes = [log for log in all_logs if log.get("chore_id") == chore_id and log.get("action") == "vote_pending"]

    return {
        "chore_id": chore_id,
        "yes_count": len(yes_votes),
        "no_count": len(no_votes),
        "pending_count": len(pending_votes),
        "total_votes": len(yes_votes) + len(no_votes) + len(pending_votes),
        "all_votes_cast": len(pending_votes) == 0,
    }
