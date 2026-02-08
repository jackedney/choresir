"""Unit tests for conflict_service module."""

from datetime import datetime

import pytest

# KeyError replaced with KeyError
from src.domain.chore import ChoreState
from src.domain.user import UserRole, UserStatus
from src.services import chore_service, conflict_service, verification_service
from src.services.conflict_service import VoteChoice, VoteResult


@pytest.fixture
async def common_users(patched_db):
    """Create common test users used across tests with well-known IDs."""
    user1 = await patched_db.create_record(
        "members",
        {
            "id": "user1",
            "phone": "+1000000001",
            "name": "User 1",
            "email": "user1@test.com",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        },
    )
    claimer = await patched_db.create_record(
        "members",
        {
            "id": "claimer",
            "phone": "+1000000002",
            "name": "Claimer",
            "email": "claimer@test.com",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        },
    )
    rejecter = await patched_db.create_record(
        "members",
        {
            "id": "rejecter",
            "phone": "+1000000003",
            "name": "Rejecter",
            "email": "rejecter@test.com",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        },
    )
    return {"user1": user1, "claimer": claimer, "rejecter": rejecter}


@pytest.mark.unit
class TestInitiateVote:
    """Tests for initiate_vote function."""

    @pytest.fixture
    async def conflict_chore_with_logs(self, patched_db):
        """Create a chore in CONFLICT state with claim and rejection logs."""
        # Create users
        claimer = await patched_db.create_record(
            "members",
            {
                "phone": "+1111111111",
                "name": "Claimer",
                "email": "claimer@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        rejecter = await patched_db.create_record(
            "members",
            {
                "phone": "+2222222222",
                "name": "Rejecter",
                "email": "rejecter@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )

        voter1 = await patched_db.create_record(
            "members",
            {
                "phone": "+3333333333",
                "name": "Voter 1",
                "email": "voter1@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        voter2 = await patched_db.create_record(
            "members",
            {
                "phone": "+4444444444",
                "name": "Voter 2",
                "email": "voter2@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )

        # Create chore and move to conflict
        chore = await chore_service.create_chore(
            title="Conflict Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=voter1["id"],
        )

        # Claim
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=claimer["id"],
            notes="Done",
        )

        # Manually create rejection log to avoid triggering initiate_vote via verify_chore
        await patched_db.create_record(
            "logs",
            {
                "chore_id": chore["id"],
                "user_id": rejecter["id"],
                "action": "reject_verification",
                "notes": "Not good",
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Manually move to conflict
        conflict_chore = await chore_service.move_to_conflict(chore_id=chore["id"])

        return {"chore": conflict_chore, "voters": [voter1, voter2]}

    async def test_initiate_vote_success(self, patched_db, conflict_chore_with_logs):
        """Test initiating a vote creates vote placeholders."""
        chore_id = conflict_chore_with_logs["chore"]["id"]

        vote_records = await conflict_service.initiate_vote(chore_id=chore_id)

        # Should create vote records for eligible voters
        # Note: includes all active users created in fixture (4 users total)
        assert len(vote_records) >= 2  # At least the 2 voters we explicitly created
        assert all(vote["action"] == "vote_pending" for vote in vote_records)
        assert all(vote["chore_id"] == chore_id for vote in vote_records)

    async def test_initiate_vote_not_in_conflict_fails(self, patched_db):
        """Test initiating vote on non-conflict chore fails."""
        # Create chore in TODO state
        chore = await chore_service.create_chore(
            title="TODO Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        with pytest.raises(ValueError, match="Cannot initiate vote"):
            await conflict_service.initiate_vote(chore_id=chore["id"])

    async def test_initiate_vote_chore_not_found(self, patched_db):
        """Test initiating vote on non-existent chore raises error."""
        with pytest.raises(KeyError):
            await conflict_service.initiate_vote(chore_id="nonexistent_id")


@pytest.mark.unit
class TestCastVote:
    """Tests for cast_vote function."""

    @pytest.fixture
    async def conflict_with_initiated_vote(self, patched_db):
        """Create a conflict with votes initiated."""
        # Create voters
        voter1 = await patched_db.create_record(
            "members",
            {
                "phone": "+1111111111",
                "name": "Voter 1",
                "email": "voter1@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        claimer = await patched_db.create_record(
            "members",
            {
                "phone": "+2222222222",
                "name": "Claimer",
                "email": "claimer@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        rejecter = await patched_db.create_record(
            "members",
            {
                "phone": "+3333333333",
                "name": "Rejecter",
                "email": "rejecter@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )

        # Create conflict chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=voter1["id"],
        )

        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=claimer["id"],
            notes="Done",
        )

        # verify_chore initiates vote automatically on REJECT
        conflict_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=rejecter["id"],
            decision=verification_service.VerificationDecision.REJECT,
            reason="No",
        )

        return {"chore": conflict_chore, "voter": voter1}

    async def test_cast_vote_yes(self, patched_db, conflict_with_initiated_vote):
        """Test casting a YES vote."""
        chore_id = conflict_with_initiated_vote["chore"]["id"]
        voter_id = conflict_with_initiated_vote["voter"]["id"]

        result = await conflict_service.cast_vote(
            chore_id=chore_id,
            voter_user_id=voter_id,
            choice=VoteChoice.YES,
        )

        assert result["action"] == "vote_yes"
        assert result["chore_id"] == chore_id
        assert result["user_id"] == voter_id

    async def test_cast_vote_no(self, patched_db, conflict_with_initiated_vote):
        """Test casting a NO vote."""
        chore_id = conflict_with_initiated_vote["chore"]["id"]
        voter_id = conflict_with_initiated_vote["voter"]["id"]

        result = await conflict_service.cast_vote(
            chore_id=chore_id,
            voter_user_id=voter_id,
            choice=VoteChoice.NO,
        )

        assert result["action"] == "vote_no"

    async def test_cast_vote_duplicate_fails(self, patched_db, conflict_with_initiated_vote):
        """Test casting vote twice fails."""
        chore_id = conflict_with_initiated_vote["chore"]["id"]
        voter_id = conflict_with_initiated_vote["voter"]["id"]

        # Cast first vote
        await conflict_service.cast_vote(
            chore_id=chore_id,
            voter_user_id=voter_id,
            choice=VoteChoice.YES,
        )

        # Try to cast second vote - should fail because either:
        # 1. Already voted check catches it, or
        # 2. No pending vote record found
        with pytest.raises((ValueError, KeyError)):
            await conflict_service.cast_vote(
                chore_id=chore_id,
                voter_user_id=voter_id,
                choice=VoteChoice.NO,
            )

    async def test_cast_vote_no_pending_record_fails(self, patched_db, common_users):
        """Test casting vote without pending vote record fails."""
        # Create conflict chore but don't initiate voting (requires manual steps)
        # Note: verify_chore initiates voting, so we must manually move to conflict
        chore = await chore_service.create_chore(
            title="Test",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=common_users["user1"]["id"],
        )

        # Move to pending verification first
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=common_users["claimer"]["id"],
            notes="Done",
        )

        # Manually move to conflict to avoid initiating votes
        conflict_chore = await chore_service.move_to_conflict(chore_id=chore["id"])

        with pytest.raises(KeyError, match="No pending vote found"):
            await conflict_service.cast_vote(
                chore_id=conflict_chore["id"],
                voter_user_id="random_voter",
                choice=VoteChoice.YES,
            )


@pytest.mark.unit
class TestTallyVotes:
    """Tests for tally_votes function."""

    @pytest.fixture
    async def setup_vote_scenario(self, patched_db):
        """Helper to create a conflict with votes."""

        async def _create_scenario(num_yes, num_no):
            # Create claimer and rejecter (these are excluded from voting)
            claimer = await patched_db.create_record(
                "members",
                {
                    "phone": "+9000000002",
                    "name": "Claimer",
                    "email": "claimer@test.com",
                    "role": UserRole.MEMBER,
                    "status": UserStatus.ACTIVE,
                    "password": "pass",
                    "passwordConfirm": "pass",
                },
            )
            rejecter = await patched_db.create_record(
                "members",
                {
                    "phone": "+9000000003",
                    "name": "Rejecter",
                    "email": "rejecter@test.com",
                    "role": UserRole.MEMBER,
                    "status": UserStatus.ACTIVE,
                    "password": "pass",
                    "passwordConfirm": "pass",
                },
            )

            # Create voters - these are the only users who will vote
            voters = []
            for i in range(num_yes + num_no):
                voter = await patched_db.create_record(
                    "members",
                    {
                        "phone": f"+{str(i).zfill(10)}",
                        "name": f"Voter {i}",
                        "email": f"voter{i}@test.com",
                        "role": UserRole.MEMBER,
                        "status": UserStatus.ACTIVE,
                        "password": "pass",
                        "passwordConfirm": "pass",
                    },
                )
                voters.append(voter)

            # Create conflict - assign to claimer (who is excluded from voting)
            chore = await chore_service.create_chore(
                title="Vote Test",
                description="Test",
                recurrence="0 10 * * *",
                assigned_to=claimer["id"],
            )

            await verification_service.request_verification(
                chore_id=chore["id"],
                claimer_user_id=claimer["id"],
                notes="Done",
            )

            # verify_chore initiates votes automatically
            conflict_chore = await verification_service.verify_chore(
                chore_id=chore["id"],
                verifier_user_id=rejecter["id"],
                decision=verification_service.VerificationDecision.REJECT,
                reason="No",
            )

            # Cast votes for all voters
            for i in range(num_yes):
                await conflict_service.cast_vote(
                    chore_id=conflict_chore["id"],
                    voter_user_id=voters[i]["id"],
                    choice=VoteChoice.YES,
                )

            for i in range(num_yes, num_yes + num_no):
                await conflict_service.cast_vote(
                    chore_id=conflict_chore["id"],
                    voter_user_id=voters[i]["id"],
                    choice=VoteChoice.NO,
                )

            return conflict_chore

        return _create_scenario

    async def test_tally_votes_approved(self, patched_db, setup_vote_scenario):
        """Test tally when YES votes win."""
        chore = await setup_vote_scenario(3, 1)  # 3 YES, 1 NO

        result, updated_chore = await conflict_service.tally_votes(chore_id=chore["id"])

        assert result == VoteResult.APPROVED
        assert updated_chore["current_state"] == ChoreState.COMPLETED

    async def test_tally_votes_rejected(self, patched_db, setup_vote_scenario):
        """Test tally when NO votes win."""
        chore = await setup_vote_scenario(1, 3)  # 1 YES, 3 NO

        result, updated_chore = await conflict_service.tally_votes(chore_id=chore["id"])

        assert result == VoteResult.REJECTED
        assert updated_chore["current_state"] == ChoreState.TODO

    async def test_tally_votes_deadlock(self, patched_db, setup_vote_scenario):
        """Test tally when votes are tied (deadlock)."""
        chore = await setup_vote_scenario(2, 2)  # 2 YES, 2 NO (tie)

        result, updated_chore = await conflict_service.tally_votes(chore_id=chore["id"])

        assert result == VoteResult.DEADLOCK
        assert updated_chore["current_state"] == ChoreState.DEADLOCK

    async def test_tally_votes_pending_votes_fails(self, patched_db, common_users):
        """Test tally fails if not all votes are cast."""
        # Create scenario with 2 voters but don't cast votes
        chore = await chore_service.create_chore(
            title="Test",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=common_users["user1"]["id"],
        )

        # Create voters
        for i in range(2):
            await patched_db.create_record(
                "members",
                {
                    "phone": f"+{str(i).zfill(10)}",
                    "name": f"Voter {i}",
                    "email": f"voter{i}@test.com",
                    "role": UserRole.MEMBER,
                    "status": UserStatus.ACTIVE,
                    "password": "pass",
                    "passwordConfirm": "pass",
                },
            )

        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=common_users["claimer"]["id"],
            notes="Done",
        )

        # verify_chore initiates votes automatically
        conflict_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=common_users["rejecter"]["id"],
            decision=verification_service.VerificationDecision.REJECT,
            reason="No",
        )

        # Try to tally without all votes cast
        with pytest.raises(ValueError, match="votes still pending"):
            await conflict_service.tally_votes(chore_id=conflict_chore["id"])


@pytest.mark.unit
class TestGetVoteStatus:
    """Tests for get_vote_status function."""

    async def test_get_vote_status_complete(self, patched_db):
        """Test getting vote status when all votes are cast."""
        # Create claimer and rejecter (excluded from voting)
        claimer = await patched_db.create_record(
            "members",
            {
                "phone": "+9000000001",
                "name": "Claimer",
                "email": "claimer@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        rejecter = await patched_db.create_record(
            "members",
            {
                "phone": "+9000000002",
                "name": "Rejecter",
                "email": "rejecter@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )

        # Create 2 voters
        voters = []
        for i in range(2):
            voter = await patched_db.create_record(
                "members",
                {
                    "phone": f"+{str(i).zfill(10)}",
                    "name": f"Voter {i}",
                    "email": f"voter{i}@test.com",
                    "role": UserRole.MEMBER,
                    "status": UserStatus.ACTIVE,
                    "password": "pass",
                    "passwordConfirm": "pass",
                },
            )
            voters.append(voter)

        # Create scenario - assign to claimer (excluded from voting)
        chore = await chore_service.create_chore(
            title="Test",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=claimer["id"],
        )

        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=claimer["id"],
            notes="Done",
        )

        # verify_chore initiates votes automatically
        conflict_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=rejecter["id"],
            decision=verification_service.VerificationDecision.REJECT,
            reason="No",
        )

        # Cast votes
        await conflict_service.cast_vote(
            chore_id=conflict_chore["id"],
            voter_user_id=voters[0]["id"],
            choice=VoteChoice.YES,
        )
        await conflict_service.cast_vote(
            chore_id=conflict_chore["id"],
            voter_user_id=voters[1]["id"],
            choice=VoteChoice.NO,
        )

        status = await conflict_service.get_vote_status(chore_id=conflict_chore["id"])

        assert status["yes_count"] == 1
        assert status["no_count"] == 1
        assert status["pending_count"] == 0
        assert status["total_votes"] == 2
        assert status["all_votes_cast"] is True

    async def test_get_vote_status_pending(self, patched_db):
        """Test getting vote status when votes are still pending."""
        # Create claimer and rejecter (excluded from voting)
        claimer = await patched_db.create_record(
            "members",
            {
                "phone": "+9000000001",
                "name": "Claimer",
                "email": "claimer@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )
        rejecter = await patched_db.create_record(
            "members",
            {
                "phone": "+9000000002",
                "name": "Rejecter",
                "email": "rejecter@test.com",
                "role": UserRole.MEMBER,
                "status": UserStatus.ACTIVE,
                "password": "pass",
                "passwordConfirm": "pass",
            },
        )

        # Create 2 voters
        for i in range(2):
            await patched_db.create_record(
                "members",
                {
                    "phone": f"+{str(i).zfill(10)}",
                    "name": f"Voter {i}",
                    "email": f"voter{i}@test.com",
                    "role": UserRole.MEMBER,
                    "status": UserStatus.ACTIVE,
                    "password": "pass",
                    "passwordConfirm": "pass",
                },
            )

        chore = await chore_service.create_chore(
            title="Test",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=claimer["id"],
        )

        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=claimer["id"],
            notes="Done",
        )

        # verify_chore initiates votes automatically
        conflict_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=rejecter["id"],
            decision=verification_service.VerificationDecision.REJECT,
            reason="No",
        )

        status = await conflict_service.get_vote_status(chore_id=conflict_chore["id"])

        assert status["yes_count"] == 0
        assert status["no_count"] == 0
        assert status["pending_count"] == 2
        assert status["total_votes"] == 2
        assert status["all_votes_cast"] is False
