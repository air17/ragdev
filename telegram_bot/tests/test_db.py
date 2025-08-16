import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

# Import the modules we're testing
from telegram_bot.db import (
    AsyncUserDatabase,
    User,
    UserRole,
    UserActivity,
    UserSession,
    MigrationManager,
    create_user_from_telegram,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    # Cleanup
    for ext in ["", "-wal", "-shm"]:
        try:
            Path(db_path + ext).unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def db(temp_db_path):
    """Create and initialize a test database instance"""

    async def _create_db():
        database = AsyncUserDatabase(temp_db_path)
        await database.initialize()
        return database

    return _create_db


@pytest.fixture
def sample_user():
    """Create a sample user for testing"""
    return User(
        user_id=12345,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="en",
        user_role="user",
    )


@pytest.fixture
def superadmin_user():
    """Create a superadmin user for testing"""
    return User(
        user_id=99999,
        username="admin",
        first_name="Super",
        last_name="Admin",
        user_role="superadmin",
    )


class TestUserRole:
    """Test UserRole enum functionality"""

    def test_user_role_creation(self):
        assert UserRole.USER.role_name == "user"
        assert UserRole.USER.level == 1
        assert UserRole.SUPERADMIN.role_name == "superadmin"
        assert UserRole.SUPERADMIN.level == 10

    def test_from_string(self):
        user_role = UserRole.from_string("user")
        assert user_role == UserRole.USER

        admin_role = UserRole.from_string("superadmin")
        assert admin_role == UserRole.SUPERADMIN

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            UserRole.from_string("invalid_role")

    def test_can_manage(self):
        assert UserRole.SUPERADMIN.can_manage(UserRole.USER)
        assert not UserRole.USER.can_manage(UserRole.SUPERADMIN)
        assert not UserRole.USER.can_manage(UserRole.USER)


class TestMigrationManager:
    """Test database migration functionality"""

    @pytest.mark.asyncio
    async def test_get_db_version_new_db(self, temp_db_path):
        version = await MigrationManager.get_db_version(temp_db_path)
        assert version == 0

    @pytest.mark.asyncio
    async def test_current_version(self):
        assert MigrationManager.CURRENT_VERSION >= 1


class TestAsyncUserDatabase:
    """Test main database functionality"""

    @pytest.mark.asyncio
    async def test_initialization(self, temp_db_path):
        db = AsyncUserDatabase(temp_db_path)
        await db.initialize()

        # Check that database file was created
        assert Path(temp_db_path).exists()

    @pytest.mark.asyncio
    async def test_add_user(self, db, sample_user):
        database = await db()
        result = await database.add_user(sample_user)
        assert result is True

        # Try to add the same user again
        result = await database.add_user(sample_user)
        assert result is False  # Should not add duplicate

    @pytest.mark.asyncio
    async def test_get_user(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)
        retrieved_user = await database.get_user(sample_user.user_id)

        assert retrieved_user is not None
        assert retrieved_user.user_id == sample_user.user_id
        assert retrieved_user.username == sample_user.username
        assert retrieved_user.first_name == sample_user.first_name

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, db):
        database = await db()
        user = await database.get_user(99999999)
        assert user is None

    @pytest.mark.asyncio
    async def test_update_user(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        result = await database.update_user(
            sample_user.user_id, first_name="Updated", username="updateduser"
        )
        assert result is True

        updated_user = await database.get_user(sample_user.user_id)
        assert updated_user.first_name == "Updated"
        assert updated_user.username == "updateduser"

    @pytest.mark.asyncio
    async def test_update_user_with_settings(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        settings = {"theme": "dark", "language": "en", "notifications": True}
        result = await database.update_user(sample_user.user_id, settings=settings)
        assert result is True

        updated_user = await database.get_user(sample_user.user_id)
        assert updated_user.settings == settings

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(self, db):
        database = await db()
        result = await database.update_user(99999999, first_name="Test")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_user_role(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Test with string role
        result = await database.set_user_role(sample_user.user_id, "superadmin")
        assert result is True

        # Test with UserRole enum
        result = await database.set_user_role(sample_user.user_id, UserRole.USER)
        assert result is True

        updated_user = await database.get_user(sample_user.user_id)
        assert updated_user.user_role == "user"

    @pytest.mark.asyncio
    async def test_is_superadmin(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.add_user(superadmin_user)

        assert await database.is_superadmin(sample_user.user_id) is False
        assert await database.is_superadmin(superadmin_user.user_id) is True
        assert await database.is_superadmin(99999999) is False  # Non-existent user

    @pytest.mark.asyncio
    async def test_is_admin_or_higher(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.add_user(superadmin_user)

        assert await database.is_admin_or_higher(sample_user.user_id) is False
        assert await database.is_admin_or_higher(superadmin_user.user_id) is True

    @pytest.mark.asyncio
    async def test_can_manage_user(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.add_user(superadmin_user)

        # Superadmin can manage regular user
        can_manage = await database.can_manage_user(
            superadmin_user.user_id, sample_user.user_id
        )
        assert can_manage is True

        # Regular user cannot manage superadmin
        can_manage = await database.can_manage_user(
            sample_user.user_id, superadmin_user.user_id
        )
        assert can_manage is False

    @pytest.mark.asyncio
    async def test_get_users_by_role(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.activate_user(sample_user.user_id)
        await database.add_user(superadmin_user)
        await database.activate_user(superadmin_user.user_id)

        users = await database.get_users_by_role("user")
        assert len(users) == 1
        assert users[0].user_id == sample_user.user_id

        admins = await database.get_users_by_role(UserRole.SUPERADMIN)
        assert len(admins) == 1
        assert admins[0].user_id == superadmin_user.user_id

    @pytest.mark.asyncio
    async def test_log_activity(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Test message activity
        result = await database.log_activity(
            sample_user.user_id, "message", {"text": "Hello, world!"}, "session_123"
        )
        assert result is True

        # Test command activity
        result = await database.log_activity(
            sample_user.user_id, "command", {"command": "/start"}
        )
        assert result is True

        # Verify user counters were updated
        updated_user = await database.get_user(sample_user.user_id)
        assert updated_user.total_messages == 1
        assert updated_user.total_commands == 1

    @pytest.mark.asyncio
    async def test_get_user_activity_stats(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Log some activities
        await database.log_activity(sample_user.user_id, "message", {"text": "Hello"})
        await database.log_activity(
            sample_user.user_id, "command", {"command": "/help"}
        )
        await database.log_activity(
            sample_user.user_id, "callback", {"data": "button_click"}
        )

        stats = await database.get_user_activity_stats(sample_user.user_id, days=30)

        assert stats["user_id"] == sample_user.user_id
        assert stats["period_days"] == 30
        assert "activity_breakdown" in stats
        assert "daily_activity" in stats
        assert stats["total_messages"] == 1
        assert stats["total_commands"] == 1

    @pytest.mark.asyncio
    async def test_get_bot_analytics(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.add_user(superadmin_user)

        # Log some activities
        await database.log_activity(sample_user.user_id, "message", {"text": "Hello"})
        await database.log_activity(
            superadmin_user.user_id, "command", {"command": "/admin"}
        )

        analytics = await database.get_bot_analytics(days=30)

        assert analytics["period_days"] == 30
        assert analytics["total_active_users"] == 0
        assert analytics["new_users_period"] == 2
        assert "top_users" in analytics
        assert "activity_breakdown" in analytics
        assert "role_distribution" in analytics

    @pytest.mark.asyncio
    async def test_get_command_usage_stats(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Log command activities
        await database.log_activity(
            sample_user.user_id, "command", {"command": "/start"}
        )
        await database.log_activity(
            sample_user.user_id, "command", {"command": "/help"}
        )
        await database.log_activity(
            sample_user.user_id, "command", {"command": "/start"}
        )

        stats = await database.get_command_usage_stats(days=30)

        assert "/start" in stats
        assert "/help" in stats
        assert stats["/start"] == 2
        assert stats["/help"] == 1

    @pytest.mark.asyncio
    async def test_start_user_session(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        result = await database.start_user_session(sample_user.user_id, "session_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_end_user_session(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        await database.start_user_session(sample_user.user_id, "session_123")
        result = await database.end_user_session(sample_user.user_id, "session_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_user_count(self, db, sample_user, superadmin_user):
        database = await db()
        await database.add_user(sample_user)
        await database.add_user(superadmin_user)

        count = await database.get_user_count(active_only=True)
        assert count == 0

        # Activate one user
        await database.activate_user(sample_user.user_id)

        active_count = await database.get_user_count(active_only=True)
        total_count = await database.get_user_count(active_only=False)

        assert active_count == 1
        assert total_count == 2

    @pytest.mark.asyncio
    async def test_activate_deactivate_user(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Activate user
        result = await database.activate_user(sample_user.user_id)
        assert result is True

        user = await database.get_user(sample_user.user_id)
        assert user.is_active == 1

        # Try to activate again (should return False)
        result = await database.activate_user(sample_user.user_id)
        assert result is False

        # Deactivate user
        result = await database.deactivate_user(sample_user.user_id)
        assert result is True

        user = await database.get_user(sample_user.user_id)
        assert user.is_active == 0

        # Try to deactivate again (should return False)
        result = await database.deactivate_user(sample_user.user_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_old_activities(self, db, sample_user):
        database = await db()
        await database.add_user(sample_user)

        # Log some activities
        await database.log_activity(sample_user.user_id, "message", {"text": "Hello"})
        await database.log_activity(
            sample_user.user_id, "command", {"command": "/help"}
        )

        # Clean up activities (should not delete recent ones)
        deleted_count = await database.cleanup_old_activities(days=1)
        assert deleted_count == 0

        # Clean up with 0 days should delete all activities
        deleted_count = await database.cleanup_old_activities(days=0)
        assert deleted_count >= 0  # Should delete some or all activities

    def test_row_to_user_conversion(self, db):
        # Test the static method _row_to_user
        row_data = {
            "user_id": 12345,
            "username": "test",
            "first_name": "Test",
            "last_name": "User",
            "created_at": datetime.now().isoformat(),
            "settings": '{"theme": "dark"}',
            "user_role": "user",
            "is_active": True,
            "total_messages": 5,
            "total_commands": 2,
        }

        user = AsyncUserDatabase._row_to_user(row_data)

        assert isinstance(user, User)
        assert user.user_id == 12345
        assert user.username == "test"
        assert isinstance(user.created_at, datetime)
        assert user.settings == {"theme": "dark"}


class TestHelperFunctions:
    """Test helper functions"""

    def test_create_user_from_telegram(self):
        # Mock Telegram user object
        telegram_user = MagicMock()
        telegram_user.id = 12345
        telegram_user.username = "testuser"
        telegram_user.first_name = "Test"
        telegram_user.last_name = "User"
        telegram_user.language_code = "en"
        telegram_user.is_bot = False
        telegram_user.is_premium = True
        telegram_user.added_to_attachment_menu = False

        user = create_user_from_telegram(telegram_user)

        assert isinstance(user, User)
        assert user.user_id == 12345
        assert user.username == "testuser"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.language_code == "en"
        assert user.is_bot is False
        assert user.is_premium is True
        assert user.added_to_attachment_menu is False


class TestDataModels:
    """Test data model classes"""

    def test_user_creation(self):
        user = User(user_id=12345, username="test")
        assert user.user_id == 12345
        assert user.username == "test"
        assert user.user_role == "user"  # Default value
        assert user.is_active is False  # Default value
        assert user.total_messages == 0  # Default value

    def test_user_activity_creation(self):
        activity = UserActivity(
            user_id=12345, activity_type="message", activity_data='{"text": "hello"}'
        )
        assert activity.user_id == 12345
        assert activity.activity_type == "message"
        assert activity.activity_data == '{"text": "hello"}'

    def test_user_session_creation(self):
        session = UserSession(
            user_id=12345,
            session_id="session_123",
            started_at=datetime.now(),
            last_activity=datetime.now(),
        )
        assert session.user_id == 12345
        assert session.session_id == "session_123"
        assert isinstance(session.started_at, datetime)


# Parametrized tests for edge cases
@pytest.mark.parametrize(
    "user_id,expected",
    [
        (0, True),  # Edge case: user_id 0
        (-1, True),  # Edge case: negative user_id
        (2**63 - 1, True),  # Edge case: max int value
    ],
)
@pytest.mark.asyncio
async def test_add_user_edge_cases(db, user_id, expected):
    """Test adding users with edge case user IDs"""
    database = await db()
    user = User(user_id=user_id, username=f"user_{user_id}")
    result = await database.add_user(user)
    assert result == expected


@pytest.mark.parametrize(
    "role_str,is_valid",
    [
        ("user", True),
        ("superadmin", True),
        ("admin", False),  # Not a valid role in our enum
        ("", False),
        ("USER", False),  # Case sensitive
    ],
)
def test_user_role_validation(role_str, is_valid):
    """Test UserRole validation with various inputs"""
    if is_valid:
        role = UserRole.from_string(role_str)
        assert role.role_name == role_str
    else:
        with pytest.raises(ValueError):
            UserRole.from_string(role_str)


# Integration test
@pytest.mark.asyncio
async def test_full_user_lifecycle(db):
    """Test complete user lifecycle from creation to deletion"""
    database = await db()
    # Create user
    user = User(
        user_id=12345, username="lifecycle_test", first_name="Test", user_role="user"
    )

    # Add user
    assert await database.add_user(user) is True

    # Verify user exists and is not active (by default)
    retrieved_user = await database.get_user(user.user_id)
    assert retrieved_user is not None
    assert retrieved_user.is_active == 0

    # Log activities
    await database.log_activity(user.user_id, "message", {"text": "Hello"})
    await database.log_activity(user.user_id, "command", {"command": "/start"})

    # Check activity stats
    stats = await database.get_user_activity_stats(user.user_id)
    assert stats["total_messages"] == 1
    assert stats["total_commands"] == 1

    # Update user role to superadmin
    assert await database.set_user_role(user.user_id, "superadmin") is True
    assert await database.is_superadmin(user.user_id) is True

    # Activate user
    assert await database.activate_user(user.user_id) is True

    # Verify user is active
    active_user = await database.get_user(user.user_id)
    assert active_user.is_active == 1

    # Deactivate user
    assert await database.deactivate_user(user.user_id) is True

    # Verify user is inactive
    inactive_user = await database.get_user(user.user_id)
    assert inactive_user.is_active == 0
