"""Unit tests for personal verification service."""

from datetime import datetime, timedelta

import pytest

from src.core import db_client
from src.services import personal_chore_service, personal_verification_service


@pytest.mark.unit
class TestLogPersonalChore:
    async def test_self_verified_no_partner(self, patched_db):
        """Test logging a chore without accountability partner."""
        # Create chore without partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
        )

        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
            notes="Good workout",
        )

        assert log.verification_status == "SELF_VERIFIED"
        assert log.accountability_partner_phone == ""
        assert log.notes == "Good workout"
        assert log.personal_chore_id == chore["id"]
        assert log.owner_phone == "+15551234567"

    async def test_pending_with_active_partner(self, patched_db):
        """Test logging a chore with active accountability partner."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        assert log.verification_status == "PENDING"
        assert log.accountability_partner_phone == "+15559999999"

    async def test_auto_convert_inactive_partner(self, patched_db):
        """Test auto-converting to self-verified when partner is inactive."""
        # Create inactive partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "inactive",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        assert log.verification_status == "SELF_VERIFIED"
        assert log.accountability_partner_phone == ""

    async def test_auto_convert_missing_partner(self, patched_db):
        """Test auto-converting to self-verified when partner doesn't exist."""
        # Create chore with non-existent partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",  # Doesn't exist
        )

        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        assert log.verification_status == "SELF_VERIFIED"
        assert log.accountability_partner_phone == ""

    async def test_log_wrong_owner(self, patched_db):
        """Test logging a chore with wrong owner raises PermissionError."""
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
        )

        with pytest.raises(PermissionError):
            await personal_verification_service.log_personal_chore(
                chore_id=chore["id"],
                owner_phone="+15559999999",  # Wrong owner
            )

    async def test_log_nonexistent_chore(self, patched_db):
        """Test logging a non-existent chore raises KeyError."""
        with pytest.raises(KeyError):
            await personal_verification_service.log_personal_chore(
                chore_id="nonexistent",
                owner_phone="+15551234567",
            )


@pytest.mark.unit
class TestVerifyPersonalChore:
    async def test_approve_pending_log(self, patched_db):
        """Test approving a pending verification."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore (creates PENDING log)
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Approve verification
        updated_log = await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone="+15559999999",
            approved=True,
            feedback="Good job!",
        )

        assert updated_log.verification_status == "VERIFIED"
        assert updated_log.partner_feedback == "Good job!"

    async def test_reject_pending_log(self, patched_db):
        """Test rejecting a pending verification."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Reject verification
        updated_log = await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone="+15559999999",
            approved=False,
            feedback="Try harder next time",
        )

        assert updated_log.verification_status == "REJECTED"
        assert updated_log.partner_feedback == "Try harder next time"

    async def test_verify_wrong_partner(self, patched_db):
        """Test verifying with wrong partner raises PermissionError."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Try to verify with wrong partner
        with pytest.raises(PermissionError, match="Only accountability partner"):
            await personal_verification_service.verify_personal_chore(
                log_id=log.id,
                verifier_phone="+15558888888",  # Wrong partner
                approved=True,
            )

    async def test_verify_already_verified_log(self, patched_db):
        """Test verifying an already verified log raises ValueError."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore (creates PENDING log)
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Verify it first
        await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone="+15559999999",
            approved=True,
        )

        # Try to verify already verified log
        with pytest.raises(ValueError, match="Cannot verify log in state"):
            await personal_verification_service.verify_personal_chore(
                log_id=log.id,
                verifier_phone="+15559999999",
                approved=True,
            )

    async def test_verify_nonexistent_log(self, patched_db):
        """Test verifying a non-existent log raises KeyError."""
        with pytest.raises(KeyError):
            await personal_verification_service.verify_personal_chore(
                log_id="nonexistent",
                verifier_phone="+15559999999",
                approved=True,
            )


@pytest.mark.unit
class TestGetPendingPartnerVerifications:
    async def test_get_pending_verifications(self, patched_db):
        """Test getting pending verifications for a partner."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create two chores with partner
        chore1 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        chore2 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Meditation",
            recurrence="every morning",
            accountability_partner_phone="+15559999999",
        )

        # Log both chores
        await personal_verification_service.log_personal_chore(
            chore_id=chore1["id"],
            owner_phone="+15551234567",
        )

        await personal_verification_service.log_personal_chore(
            chore_id=chore2["id"],
            owner_phone="+15551234567",
        )

        # Get pending verifications
        pending = await personal_verification_service.get_pending_partner_verifications(
            partner_phone="+15559999999",
        )

        assert len(pending) == 2
        assert all(log.verification_status == "PENDING" for log in pending)
        assert any(log.chore_title == "Gym" for log in pending)
        assert any(log.chore_title == "Meditation" for log in pending)

    async def test_get_pending_verifications_filters_verified(self, patched_db):
        """Test that verified logs are not included in pending verifications."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Verify it
        await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone="+15559999999",
            approved=True,
        )

        # Get pending verifications (should be empty)
        pending = await personal_verification_service.get_pending_partner_verifications(
            partner_phone="+15559999999",
        )

        assert len(pending) == 0

    async def test_get_pending_verifications_empty(self, patched_db):
        """Test getting pending verifications when there are none."""
        pending = await personal_verification_service.get_pending_partner_verifications(
            partner_phone="+15559999999",
        )

        assert pending == []


@pytest.mark.unit
class TestAutoVerifyExpiredLogs:
    async def test_auto_verify_expired_logs(self, patched_db):
        """Test auto-verifying logs older than 48 hours."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Create an old log (49 hours ago)
        old_time = datetime.now() - timedelta(hours=49)
        old_log = await db_client.create_record(
            collection="personal_chore_logs",
            data={
                "personal_chore_id": chore["id"],
                "owner_phone": "+15551234567",
                "completed_at": old_time.isoformat(),
                "verification_status": "PENDING",
                "accountability_partner_phone": "+15559999999",
                "partner_feedback": "",
                "notes": "",
            },
        )

        # Create a recent log (1 hour ago)
        recent_time = datetime.now() - timedelta(hours=1)
        recent_log = await db_client.create_record(
            collection="personal_chore_logs",
            data={
                "personal_chore_id": chore["id"],
                "owner_phone": "+15551234567",
                "completed_at": recent_time.isoformat(),
                "verification_status": "PENDING",
                "accountability_partner_phone": "+15559999999",
                "partner_feedback": "",
                "notes": "",
            },
        )

        # Run auto-verify
        count = await personal_verification_service.auto_verify_expired_logs()

        assert count == 1

        # Check that old log was auto-verified
        updated_old = await db_client.get_record(
            collection="personal_chore_logs",
            record_id=old_log["id"],
        )
        assert updated_old["verification_status"] == "VERIFIED"
        assert "Auto-verified" in updated_old["partner_feedback"]

        # Check that recent log is still pending
        updated_recent = await db_client.get_record(
            collection="personal_chore_logs",
            record_id=recent_log["id"],
        )
        assert updated_recent["verification_status"] == "PENDING"

    async def test_auto_verify_no_expired_logs(self, patched_db):
        """Test auto-verifying when there are no expired logs."""
        count = await personal_verification_service.auto_verify_expired_logs()
        assert count == 0


@pytest.mark.unit
class TestGetPersonalStats:
    async def test_get_stats_basic(self, patched_db):
        """Test getting basic personal stats."""
        # Create chores
        chore1 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
        )

        await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Meditation",
            recurrence="every morning",
        )

        # Log completions
        await personal_verification_service.log_personal_chore(
            chore_id=chore1["id"],
            owner_phone="+15551234567",
        )

        # Get stats
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
            period_days=30,
        )

        assert stats.total_chores == 2
        assert stats.completions_this_period == 1
        assert stats.pending_verifications == 0
        assert stats.period_days == 30

    async def test_get_stats_with_pending(self, patched_db):
        """Test stats include pending verifications."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore (creates PENDING)
        await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Get stats
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
        )

        assert stats.total_chores == 1
        assert stats.completions_this_period == 0  # Pending not counted
        assert stats.pending_verifications == 1

    async def test_get_stats_completion_rate(self, patched_db):
        """Test completion rate calculation."""
        # Create 3 chores
        chore1 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
        )

        chore2 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Meditation",
            recurrence="every morning",
        )

        await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Reading",
            recurrence="every 3 days",
        )

        # Log 2 completions
        await personal_verification_service.log_personal_chore(
            chore_id=chore1["id"],
            owner_phone="+15551234567",
        )

        await personal_verification_service.log_personal_chore(
            chore_id=chore2["id"],
            owner_phone="+15551234567",
        )

        # Get stats
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
        )

        # 2 completions / 3 total chores = 66.7%
        assert stats.completion_rate == 66.7

    async def test_get_stats_no_chores(self, patched_db):
        """Test stats with no chores."""
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
        )

        assert stats.total_chores == 0
        assert stats.completions_this_period == 0
        assert stats.pending_verifications == 0
        assert stats.completion_rate == 0

    async def test_get_stats_filters_by_period(self, patched_db):
        """Test stats filter completions by period."""
        # Create chore
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
        )

        # Create old completion (outside 30 day period)
        old_time = datetime.now() - timedelta(days=40)
        await db_client.create_record(
            collection="personal_chore_logs",
            data={
                "personal_chore_id": chore["id"],
                "owner_phone": "+15551234567",
                "completed_at": old_time.isoformat(),
                "verification_status": "SELF_VERIFIED",
                "accountability_partner_phone": "",
                "partner_feedback": "",
                "notes": "",
            },
        )

        # Create recent completion
        await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Get stats for 30 days
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
            period_days=30,
        )

        # Should only count recent completion
        assert stats.completions_this_period == 1

    async def test_get_stats_excludes_rejected(self, patched_db):
        """Test stats exclude rejected verifications."""
        # Create partner user
        await db_client.create_record(
            collection="users",
            data={
                "phone": "+15559999999",
                "username": "partner",
                "status": "active",
            },
        )

        # Create chore with partner
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Gym",
            recurrence="every 2 days",
            accountability_partner_phone="+15559999999",
        )

        # Log chore
        log = await personal_verification_service.log_personal_chore(
            chore_id=chore["id"],
            owner_phone="+15551234567",
        )

        # Reject it
        await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone="+15559999999",
            approved=False,
        )

        # Get stats
        stats = await personal_verification_service.get_personal_stats(
            owner_phone="+15551234567",
        )

        # Rejected should not count as completion
        assert stats.completions_this_period == 0
        assert stats.pending_verifications == 0
