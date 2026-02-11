"""Unit tests for group_context_service module."""

from datetime import datetime, timedelta

import pytest

from src.services import group_context_service


@pytest.fixture
def patched_group_context_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
    monkeypatch.setattr("src.services.group_context_service.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.services.group_context_service.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.services.group_context_service.db_client.delete_record", in_memory_db.delete_record)
    return in_memory_db


class TestAddGroupMessage:
    """Test adding messages to group context."""

    @pytest.mark.asyncio
    async def test_adds_user_message(
        self,
        patched_group_context_db,
    ):
        """Adds a user message to group context."""
        group_id = "group123@g.us"
        sender_phone = "+1234567890"
        sender_name = "Alice"
        content = "Hello group!"

        await group_context_service.add_group_message(
            group_id=group_id,
            sender_phone=sender_phone,
            sender_name=sender_name,
            content=content,
            is_bot=False,
        )

        # Verify record was created
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 1
        assert messages[0]["group_id"] == group_id
        assert messages[0]["sender_phone"] == sender_phone
        assert messages[0]["sender_name"] == sender_name
        assert messages[0]["content"] == content
        assert messages[0]["is_bot"] is False

    @pytest.mark.asyncio
    async def test_adds_bot_message(
        self,
        patched_group_context_db,
    ):
        """Adds a bot message to group context."""
        group_id = "group123@g.us"
        sender_phone = "+19999999999"
        sender_name = "Choresir"
        content = "Hello everyone!"

        await group_context_service.add_group_message(
            group_id=group_id,
            sender_phone=sender_phone,
            sender_name=sender_name,
            content=content,
            is_bot=True,
        )

        # Verify record was created with is_bot=True
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 1
        assert messages[0]["is_bot"] is True

    @pytest.mark.asyncio
    async def test_raises_value_error_for_empty_group_id(
        self,
        patched_group_context_db,
    ):
        """Raises ValueError when group_id is empty."""
        with pytest.raises(ValueError, match="group_id cannot be empty"):
            await group_context_service.add_group_message(
                group_id="",
                sender_phone="+1234567890",
                sender_name="Alice",
                content="Hello",
                is_bot=False,
            )

    @pytest.mark.asyncio
    async def test_calculates_expires_at(
        self,
        patched_group_context_db,
    ):
        """Calculates expires_at as created_at + 60 minutes."""
        group_id = "group123@g.us"

        await group_context_service.add_group_message(
            group_id=group_id,
            sender_phone="+1234567890",
            sender_name="Alice",
            content="Hello",
            is_bot=False,
        )

        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 1

        created_at = datetime.fromisoformat(messages[0]["created_at"])
        expires_at = datetime.fromisoformat(messages[0]["expires_at"])

        # expires_at should be approximately 60 minutes after created_at
        assert expires_at - created_at == timedelta(minutes=60)


class TestGetGroupContext:
    """Test retrieving group context."""

    @pytest.mark.asyncio
    async def test_returns_messages_ordered_by_created_at(
        self,
        patched_group_context_db,
    ):
        """Returns messages in chronological order (oldest first)."""
        group_id = "group123@g.us"

        # Add messages in reverse chronological order
        for i in range(3):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": group_id,
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"User{i}",
                    "content": f"Message {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        context = await group_context_service.get_group_context(group_id=group_id)

        # Should return 3 messages in reverse order (newest first was added last)
        assert len(context) == 3
        # Since we added them sequentially, the last added is newest
        assert context[0]["sender_name"] == "User0"
        assert context[1]["sender_name"] == "User1"
        assert context[2]["sender_name"] == "User2"

    @pytest.mark.asyncio
    async def test_limits_to_max_20_messages(
        self,
        patched_group_context_db,
    ):
        """Returns only last 20 messages when more exist."""
        group_id = "group123@g.us"

        # Add 25 messages
        for i in range(25):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": group_id,
                    "sender_phone": f"+123456789{i % 10}",
                    "sender_name": f"User{i}",
                    "content": f"Message {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        context = await group_context_service.get_group_context(group_id=group_id)

        # Should return only 20 messages
        assert len(context) == 20

    @pytest.mark.asyncio
    async def test_excludes_expired_messages(
        self,
        patched_group_context_db,
    ):
        """Excludes messages older than 60 minutes."""
        group_id = "group123@g.us"

        # Add an expired message (61 minutes old)
        await patched_group_context_db.create_record(
            collection="group_context",
            data={
                "group_id": group_id,
                "sender_phone": "+1234567890",
                "sender_name": "Alice",
                "content": "Old message",
                "is_bot": False,
                "created_at": (datetime.now() - timedelta(minutes=61)).isoformat(),
                "expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
            },
        )

        # Add a fresh message
        await patched_group_context_db.create_record(
            collection="group_context",
            data={
                "group_id": group_id,
                "sender_phone": "+1234567891",
                "sender_name": "Bob",
                "content": "Fresh message",
                "is_bot": False,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
            },
        )

        context = await group_context_service.get_group_context(group_id=group_id)

        # Should only return the fresh message
        assert len(context) == 1
        assert context[0]["sender_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_messages(
        self,
        patched_group_context_db,
    ):
        """Returns empty list when group has no messages."""
        context = await group_context_service.get_group_context(group_id="group123@g.us")
        assert context == []

    @pytest.mark.asyncio
    async def test_raises_value_error_for_empty_group_id(
        self,
        patched_group_context_db,
    ):
        """Raises ValueError when group_id is empty."""
        with pytest.raises(ValueError, match="group_id cannot be empty"):
            await group_context_service.get_group_context(group_id="")

    @pytest.mark.asyncio
    async def test_filters_by_group_id(
        self,
        patched_group_context_db,
    ):
        """Only returns messages for the specified group."""
        # Add messages to group1
        for i in range(3):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group1@g.us",
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"User{i}",
                    "content": f"Message {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        # Add messages to group2
        for i in range(2):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group2@g.us",
                    "sender_phone": f"+198765432{i}",
                    "sender_name": f"Group2User{i}",
                    "content": f"Group2 Message {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        context = await group_context_service.get_group_context(group_id="group1@g.us")

        # Should only return group1's messages
        assert len(context) == 3
        assert all(msg["sender_name"].startswith("User") for msg in context)


class TestFormatGroupContextForPrompt:
    """Test formatting group context for prompts."""

    def test_formats_empty_context(self):
        """Returns empty string for empty context."""
        result = group_context_service.format_group_context_for_prompt([])
        assert result == ""

    def test_formats_single_message(self):
        """Formats a single message correctly."""
        context = [{"sender_name": "Alice", "sender_phone": "+1111111111", "content": "Hello everyone"}]
        result = group_context_service.format_group_context_for_prompt(context)

        assert "## RECENT GROUP CONVERSATION" in result
        assert "[Alice (+1111111111)]: Hello everyone" in result
        assert "shared references" in result

    def test_formats_multiple_messages(self):
        """Formats multiple messages in order."""
        context = [
            {"sender_name": "Alice", "sender_phone": "+1111111111", "content": "First message"},
            {"sender_name": "Bob", "sender_phone": "+2222222222", "content": "Second message"},
            {"sender_name": "Charlie", "sender_phone": "+3333333333", "content": "Third message"},
        ]
        result = group_context_service.format_group_context_for_prompt(context)

        assert "[Alice (+1111111111)]: First message" in result
        assert "[Bob (+2222222222)]: Second message" in result
        assert "[Charlie (+3333333333)]: Third message" in result

    def test_truncates_long_messages(self):
        """Truncates messages longer than MAX_CONTEXT_CONTENT_LENGTH."""
        long_content = "x" * 250
        context = [{"sender_name": "Alice", "sender_phone": "+1111111111", "content": long_content}]
        result = group_context_service.format_group_context_for_prompt(context)

        # Should be truncated to 200 chars plus "..."
        assert "[Alice" in result
        assert "..." in result
        alice_line = next(line for line in result.split("\n") if "[Alice" in line)
        assert len(alice_line) < 280

    def test_includes_helpful_instruction(self):
        """Includes instruction about using context for references."""
        context = [{"sender_name": "Alice", "sender_phone": "+1111111111", "content": "Hello"}]
        result = group_context_service.format_group_context_for_prompt(context)

        assert "If anyone's current message references something from this context" in result
        assert "'both'" in result
        assert "'that'" in result


class TestCleanupExpiredGroupContext:
    """Test cleanup of expired group context messages."""

    @pytest.mark.asyncio
    async def test_deletes_expired_messages(
        self,
        patched_group_context_db,
    ):
        """Deletes messages where expires_at < now."""
        # Add an expired message
        await patched_group_context_db.create_record(
            collection="group_context",
            data={
                "group_id": "group123@g.us",
                "sender_phone": "+1234567890",
                "sender_name": "Alice",
                "content": "Old message",
                "is_bot": False,
                "created_at": (datetime.now() - timedelta(minutes=61)).isoformat(),
                "expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
            },
        )

        # Add a fresh message
        await patched_group_context_db.create_record(
            collection="group_context",
            data={
                "group_id": "group123@g.us",
                "sender_phone": "+1234567891",
                "sender_name": "Bob",
                "content": "Fresh message",
                "is_bot": False,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
            },
        )

        # Run cleanup
        count = await group_context_service.cleanup_expired_group_context()

        # Should have deleted 1 expired message
        assert count == 1

        # Verify only fresh message remains
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 1
        assert messages[0]["sender_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_keeps_non_expired_messages(
        self,
        patched_group_context_db,
    ):
        """Keeps messages where expires_at >= now."""
        # Add multiple fresh messages
        for i in range(3):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group123@g.us",
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"User{i}",
                    "content": f"Message {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        # Run cleanup
        count = await group_context_service.cleanup_expired_group_context()

        # Should have deleted 0 messages
        assert count == 0

        # Verify all messages still exist
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_messages(
        self,
        patched_group_context_db,
    ):
        """Returns zero when there are no messages."""
        count = await group_context_service.cleanup_expired_group_context()

        assert count == 0

    @pytest.mark.asyncio
    async def test_deletes_multiple_expired_messages(
        self,
        patched_group_context_db,
    ):
        """Deletes multiple expired messages."""
        # Add multiple expired messages
        for i in range(3):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group123@g.us",
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"User{i}",
                    "content": f"Old message {i}",
                    "is_bot": False,
                    "created_at": (datetime.now() - timedelta(minutes=61)).isoformat(),
                    "expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
                },
            )

        # Run cleanup
        count = await group_context_service.cleanup_expired_group_context()

        # Should have deleted 3 messages
        assert count == 3

        # Verify no messages remain
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_handles_mixed_expired_and_fresh(
        self,
        patched_group_context_db,
    ):
        """Correctly handles mix of expired and fresh messages."""
        # Add expired messages
        for i in range(2):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group123@g.us",
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"ExpiredUser{i}",
                    "content": f"Expired {i}",
                    "is_bot": False,
                    "created_at": (datetime.now() - timedelta(minutes=61)).isoformat(),
                    "expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
                },
            )

        # Add fresh messages
        for i in range(3):
            await patched_group_context_db.create_record(
                collection="group_context",
                data={
                    "group_id": "group123@g.us",
                    "sender_phone": f"+123456789{i}",
                    "sender_name": f"FreshUser{i}",
                    "content": f"Fresh {i}",
                    "is_bot": False,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(),
                },
            )

        # Run cleanup
        count = await group_context_service.cleanup_expired_group_context()

        # Should have deleted 2 expired messages
        assert count == 2

        # Verify only fresh messages remain
        messages = await patched_group_context_db.list_records(collection="group_context")
        assert len(messages) == 3
        assert all(msg["sender_name"].startswith("FreshUser") for msg in messages)
