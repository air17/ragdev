import pytest
from unittest.mock import AsyncMock, Mock, patch

# Import your actual modules
from telegram_bot.main import (
    BotEventHandler,
    BotConstants,
    UserStates,
    DatabaseMiddleware,
)
from telegram_bot.db import DatabaseError


class TestBotConstants:
    """Test BotConstants class"""

    def test_role_constants(self):
        assert BotConstants.ROLE_USER == "user"
        assert BotConstants.ROLE_SUPERADMIN == "superadmin"
        assert BotConstants.ROLE_USER in BotConstants.VALID_ROLES

    def test_activity_types(self):
        assert BotConstants.ACTIVITY_COMMAND == "command"
        assert BotConstants.ACTIVITY_MESSAGE == "message"

    def test_default_values(self):
        assert BotConstants.DEFAULT_ANALYTICS_DAYS == 30


@pytest.fixture
def mock_db():
    """Mock database"""
    db = AsyncMock()
    db.add_user.return_value = True
    db.get_user.return_value = Mock(
        id=123,
        first_name="Test",
        user_role=BotConstants.ROLE_USER,
        is_active=True,
        total_messages=10,
        language_code="en",
        settings={},
    )
    db.log_activity.return_value = True
    db.start_user_session.return_value = True
    db.update_user.return_value = True
    db.is_admin_or_higher.return_value = False
    db.is_superadmin.return_value = False
    return db


@pytest.fixture
def mock_user():
    """Mock Telegram user"""
    user = Mock()
    user.id = 123456789
    user.first_name = "Test"
    user.last_name = "User"
    user.is_bot = False
    return user


@pytest.fixture
def mock_message(mock_user):
    """Mock Telegram message"""
    message = Mock()
    message.from_user = mock_user
    message.chat = Mock()
    message.chat.type = "private"
    message.text = "/start"
    message.entities = []
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_fsm_context():
    """Mock FSM context"""
    context = AsyncMock()
    context.get_state.return_value = None
    context.set_state = AsyncMock()
    context.clear = AsyncMock()
    return context


@pytest.fixture
def bot_handler(mock_db):
    """Create BotEventHandler instance"""
    return BotEventHandler(mock_db)


class TestBotEventHandler:
    """Test BotEventHandler initialization"""

    def test_init(self, mock_db):
        handler = BotEventHandler(mock_db)
        assert handler.db == mock_db
        assert handler.router is not None

    @pytest.mark.asyncio
    async def test_get_user_fsm_state_as_string(self, mock_fsm_context):
        # Test with waiting_for_name state
        mock_fsm_context.get_state.return_value = UserStates.waiting_for_name.state
        result = await BotEventHandler._get_user_fsm_state_as_string(mock_fsm_context)
        assert result == BotConstants.USER_STATE_WAITING_NAME

        # Test with no state
        mock_fsm_context.get_state.return_value = None
        result = await BotEventHandler._get_user_fsm_state_as_string(mock_fsm_context)
        assert result is None


class TestCommandHandlers:
    """Test command handlers"""

    @pytest.mark.asyncio
    async def test_handle_start_command_success(
        self, bot_handler, mock_message, mock_fsm_context
    ):
        with patch("telegram_bot.main.create_user_from_telegram") as mock_create_user:
            mock_create_user.return_value = Mock()

            await bot_handler.handle_start_command(mock_message, mock_fsm_context)

            bot_handler.db.add_user.assert_called_once()
            bot_handler.db.start_user_session.assert_called_once()
            bot_handler.db.log_activity.assert_called_once()
            mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_help_command(self, bot_handler, mock_message):
        await bot_handler.handle_help_command(mock_message)

        bot_handler.db.get_user.assert_called_once()
        bot_handler.db.log_activity.assert_called_once()
        mock_message.answer.assert_called_once()

        help_text = mock_message.answer.call_args[0][0]
        assert "/settings" in help_text

    @pytest.mark.asyncio
    async def test_handle_stats_command_regular_user(self, bot_handler, mock_message):
        bot_handler.db.get_user_activity_stats.return_value = {
            "total_messages": 50,
            "total_commands": 10,
            "first_interaction": "2023-01-01T00:00:00",
        }

        await bot_handler.handle_stats_command(mock_message)

        bot_handler.db.is_admin_or_higher.assert_called_once()
        bot_handler.db.get_user_activity_stats.assert_called_once()
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_admin_command_access_denied(self, bot_handler, mock_message):
        bot_handler.db.is_admin_or_higher.return_value = False

        await bot_handler.handle_admin_command(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Access denied" in response

    @pytest.mark.asyncio
    async def test_handle_ban_command_invalid_args(self, bot_handler, mock_message):
        bot_handler.db.is_admin_or_higher.return_value = True
        mock_message.text = "/ban"  # No user ID

        await bot_handler.handle_ban_command(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Usage:" in response


class TestFSMHandlers:
    """Test FSM handlers"""

    @pytest.mark.asyncio
    async def test_handle_name_input_success(
        self, bot_handler, mock_message, mock_fsm_context
    ):
        mock_message.text = "New Name"
        bot_handler.db.update_user.return_value = True

        await bot_handler.handle_name_input(mock_message, mock_fsm_context)

        mock_fsm_context.clear.assert_called_once()
        mock_message.answer.assert_called_once()


class TestCallbackHandlers:
    """Test callback handlers"""

    @pytest.fixture
    def mock_callback(self, mock_user):
        callback = Mock()
        callback.from_user = mock_user
        callback.data = "settings_notifications_on"
        callback.answer = AsyncMock()
        callback.message = Mock()
        callback.message.edit_text = AsyncMock()
        return callback


class TestMiddleware:
    """Test middleware"""

    @pytest.fixture
    def middleware(self, mock_db):
        return DatabaseMiddleware(mock_db)

    @pytest.mark.asyncio
    async def test_middleware_active_user(self, middleware, mock_message):
        mock_handler = AsyncMock(return_value="result")
        mock_user = Mock(is_active=True)
        middleware.db.get_user.return_value = mock_user

        with patch("telegram_bot.main.create_user_from_telegram") as mock_create:
            mock_create.return_value = Mock()

            result = await middleware(mock_handler, mock_message, {})

            middleware.db.add_user.assert_called_once()
            mock_handler.assert_called_once()
            assert result == "result"

    @pytest.mark.asyncio
    async def test_middleware_inactive_user(self, middleware, mock_message):
        mock_handler = AsyncMock()
        mock_user = Mock(is_active=False)
        middleware.db.get_user.return_value = mock_user

        with patch("telegram_bot.main.create_user_from_telegram"):
            result = await middleware(mock_handler, mock_message, {})

            mock_handler.assert_not_called()
            assert result is None


class TestErrorHandling:
    """Test error scenarios"""

    @pytest.mark.asyncio
    async def test_start_command_db_error(
        self, bot_handler, mock_message, mock_fsm_context
    ):
        bot_handler.db.add_user.side_effect = DatabaseError("DB Error")

        with patch("telegram_bot.main.create_user_from_telegram"):
            await bot_handler.handle_start_command(mock_message, mock_fsm_context)

            # Should still respond to user
            mock_message.answer.assert_called_once()
