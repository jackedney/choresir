import pytest

from src.services import personal_chore_service


@pytest.mark.unit
class TestCreatePersonalChore:
    async def test_create_recurring_chore(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Go to gym",
            recurrence="every 2 days",
        )

        assert chore["owner_phone"] == "+15551234567"
        assert chore["title"] == "Go to gym"
        assert "INTERVAL:2:" in chore["recurrence"]
        assert chore["status"] == "ACTIVE"
        assert chore["due_date"] == ""  # No due date for recurring chores

    async def test_create_one_time_chore(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Finish report",
            recurrence="by friday",
        )

        assert chore["recurrence"] == ""  # No recurring pattern
        assert chore["due_date"] != ""  # Has due date

    async def test_create_chore_with_accountability_partner(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Go to gym",
            recurrence="every morning",
            accountability_partner_phone="+15559876543",
        )

        assert chore["accountability_partner_phone"] == "+15559876543"

    async def test_create_chore_without_recurrence(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="One-time task",
        )

        assert chore["recurrence"] == ""
        assert chore["due_date"] == ""

    async def test_create_chore_every_morning(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Morning meditation",
            recurrence="every morning",
        )

        assert chore["recurrence"] == "0 8 * * *"

    async def test_create_chore_every_weekday(self, patched_db):
        chore = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Weekly meeting",
            recurrence="every friday",
        )

        assert chore["recurrence"] == "0 8 * * 5"

    async def test_create_chore_invalid_recurrence(self, patched_db):
        with pytest.raises(ValueError, match="Invalid recurrence format"):
            await personal_chore_service.create_personal_chore(
                owner_phone="+15551234567",
                title="Invalid chore",
                recurrence="invalid format",
            )


@pytest.mark.unit
class TestGetPersonalChores:
    async def test_get_chores_filters_by_owner(self, patched_db):
        # Create chores for two different users
        await personal_chore_service.create_personal_chore(
            owner_phone="+15551111111",
            title="User 1 chore",
            recurrence="every morning",
        )
        await personal_chore_service.create_personal_chore(
            owner_phone="+15552222222",
            title="User 2 chore",
            recurrence="every morning",
        )

        # User 1 should only see their chore
        chores = await personal_chore_service.get_personal_chores(owner_phone="+15551111111")

        assert len(chores) == 1
        assert chores[0]["title"] == "User 1 chore"

    async def test_get_chores_filters_by_status(self, patched_db):
        # Create an active chore
        chore1 = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Active chore",
            recurrence="every morning",
        )

        # Archive it
        await personal_chore_service.delete_personal_chore(
            chore_id=chore1["id"],
            owner_phone="+15551234567",
        )

        # Create another active chore
        await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Another active chore",
            recurrence="every morning",
        )

        # Should only get active chores
        active_chores = await personal_chore_service.get_personal_chores(
            owner_phone="+15551234567",
            status="ACTIVE",
        )
        assert len(active_chores) == 1
        assert active_chores[0]["title"] == "Another active chore"

        # Should get archived chores
        archived_chores = await personal_chore_service.get_personal_chores(
            owner_phone="+15551234567",
            status="ARCHIVED",
        )
        assert len(archived_chores) == 1
        assert archived_chores[0]["title"] == "Active chore"

    async def test_get_chores_empty_result(self, patched_db):
        chores = await personal_chore_service.get_personal_chores(owner_phone="+15559999999")
        assert chores == []


@pytest.mark.unit
class TestGetPersonalChoreById:
    async def test_get_chore_by_id_success(self, patched_db):
        created = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Test chore",
            recurrence="every morning",
        )

        retrieved = await personal_chore_service.get_personal_chore_by_id(
            chore_id=created["id"],
            owner_phone="+15551234567",
        )

        assert retrieved["id"] == created["id"]
        assert retrieved["title"] == "Test chore"

    async def test_get_chore_by_id_wrong_owner(self, patched_db):
        created = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Test chore",
            recurrence="every morning",
        )

        with pytest.raises(PermissionError, match="does not belong to"):
            await personal_chore_service.get_personal_chore_by_id(
                chore_id=created["id"],
                owner_phone="+15559999999",  # Different owner
            )

    async def test_get_chore_by_id_not_found(self, patched_db):
        with pytest.raises(KeyError):
            await personal_chore_service.get_personal_chore_by_id(
                chore_id="nonexistent",
                owner_phone="+15551234567",
            )


@pytest.mark.unit
class TestDeletePersonalChore:
    async def test_delete_chore_success(self, patched_db):
        created = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Test chore",
            recurrence="every morning",
        )

        await personal_chore_service.delete_personal_chore(
            chore_id=created["id"],
            owner_phone="+15551234567",
        )

        # Chore should be archived, not deleted
        archived = await personal_chore_service.get_personal_chore_by_id(
            chore_id=created["id"],
            owner_phone="+15551234567",
        )
        assert archived["status"] == "ARCHIVED"

    async def test_delete_chore_wrong_owner(self, patched_db):
        created = await personal_chore_service.create_personal_chore(
            owner_phone="+15551234567",
            title="Test chore",
            recurrence="every morning",
        )

        with pytest.raises(PermissionError, match="does not belong to"):
            await personal_chore_service.delete_personal_chore(
                chore_id=created["id"],
                owner_phone="+15559999999",
            )

    async def test_delete_chore_not_found(self, patched_db):
        with pytest.raises(KeyError):
            await personal_chore_service.delete_personal_chore(
                chore_id="nonexistent",
                owner_phone="+15551234567",
            )


@pytest.mark.unit
class TestFuzzyMatchPersonalChore:
    def test_exact_match(self):
        chores = [
            {"id": "1", "title": "Go to gym"},
            {"id": "2", "title": "Buy groceries"},
        ]

        result = personal_chore_service.fuzzy_match_personal_chore(chores, "go to gym")
        assert result["id"] == "1"

    def test_contains_match(self):
        chores = [
            {"id": "1", "title": "Go to the gym"},
            {"id": "2", "title": "Buy groceries"},
        ]

        result = personal_chore_service.fuzzy_match_personal_chore(chores, "gym")
        assert result["id"] == "1"

    def test_partial_word_match(self):
        chores = [
            {"id": "1", "title": "Morning meditation"},
            {"id": "2", "title": "Buy groceries"},
        ]

        result = personal_chore_service.fuzzy_match_personal_chore(chores, "meditation")
        assert result["id"] == "1"

    def test_no_match(self):
        chores = [
            {"id": "1", "title": "Go to gym"},
            {"id": "2", "title": "Buy groceries"},
        ]

        result = personal_chore_service.fuzzy_match_personal_chore(chores, "swimming")
        assert result is None

    def test_case_insensitive(self):
        chores = [
            {"id": "1", "title": "Go to gym"},
        ]

        result = personal_chore_service.fuzzy_match_personal_chore(chores, "GO TO GYM")
        assert result["id"] == "1"

    def test_empty_list(self):
        result = personal_chore_service.fuzzy_match_personal_chore([], "anything")
        assert result is None
