import asyncio
import logging
from datetime import datetime
from typing import Any

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from bleach import clean

from chat.agent import ChatAgent
from chat.sessions import ChatSessionManager
from project_management.const import PROJECTS, ProjectInfo
from project_management.git_utils import (
    get_all_branches,
    switch_branch,
    get_current_branch,
    pull_current_branch,
)
from telegram_bot import const
from telegram_bot.const import BotConstants
from telegram_bot.db import (
    AsyncUserDatabase,
    create_user_from_telegram,
    DatabaseError,
    ChatSession,
    User,
)
from telegram_bot.utils import markdown_to_telegram_html_ai, remove_non_telegram_html

MAX_MESSAGE_LENGTH: int = (
    4096  # Telegram message length limit, with buffer for html tags
)


class BotEventHandler:
    """Example class showing database method calls for different Telegram events"""

    router: Router = Router()

    cache: dict[str, Any] = {}
    ONGOING_GENERATION_CACHE_KEY = "ongoing_generation"
    STOP_GENERATION_CACHE_KEY = "stop_generation"

    def __init__(self, db: AsyncUserDatabase):
        self.db: AsyncUserDatabase = db
        self.logger = logging.getLogger(self.__class__.__name__)
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all event handlers"""
        # Message handlers
        self.router.message.register(self.handle_start_command, CommandStart())
        self.router.message.register(self.handle_help_command, Command("help"))
        self.router.message.register(self.handle_id_command, Command("id"))
        self.router.message.register(self.handle_stats_command, Command("stats"))
        self.router.message.register(self.handle_admin_command, Command("admin"))
        self.router.message.register(
            self.handle_list_users_command, Command("list_users")
        )
        self.router.message.register(self.handle_ban_command, Command("ban"))
        self.router.message.register(self.handle_activate_command, Command("activate"))
        self.router.message.register(self.handle_promote_command, Command("promote"))
        self.router.message.register(self.handle_settings_command, Command("settings"))
        # Git
        self.router.message.register(
            self.handle_list_branches_command, Command("list_branches")
        )
        self.router.message.register(
            self.handle_current_branch_command, Command("current_branch")
        )
        self.router.message.register(
            self.handle_pull_current_branch_command, Command("pull_current_branch")
        )
        self.router.message.register(
            self.handle_switch_branch_command, Command("switch_branch")
        )

        # FSM handlers
        self.router.message.register(
            self.handle_name_input, UserStates.waiting_for_name
        )

        # Chat command handlers
        self.router.message.register(
            self.handle_select_project_command, Command(commands=list(PROJECTS.keys()))
        )
        self.router.message.register(self.handle_my_chats_command, Command("my_chats"))
        self.router.message.register(self.handle_chat_command, Command("chat"))
        self.router.message.register(self.handle_end_chat_command, Command("end_chat"))
        self.router.message.register(self.handle_stop_command, Command("stop"))

        # General message handler (should be last)
        self.router.message.register(self.handle_chat_message)

        # Callback query handlers
        self.router.callback_query.register(self.handle_any_callback)

    # ==================== HELPER METHODS ====================

    @staticmethod
    async def _get_user_fsm_state_as_string(state: FSMContext) -> str | None:
        """Convert FSM state to string for database storage"""
        current_state = await state.get_state()
        if current_state is None:
            return None

        # Map FSM states to database state strings
        state_mapping = {
            UserStates.waiting_for_name.state: BotConstants.USER_STATE_WAITING_NAME,
            UserStates.in_settings.state: BotConstants.USER_STATE_SETTINGS,
        }

        return state_mapping.get(current_state)

    async def _set_user_fsm_state(self, state: FSMContext, new_state: State = None):
        """Set FSM state and update database user state"""
        if new_state:
            await state.set_state(new_state)
            db_state = await self._get_user_fsm_state_as_string(state)
        else:
            await state.clear()
            db_state = None

        return db_state

    # ==================== COMMAND HANDLERS ====================

    async def handle_start_command(self, message: Message, state: FSMContext):
        """
        /start command - First user interaction
        """
        user = create_user_from_telegram(message.from_user)

        try:
            # Register user if new (will ignore if exists)
            await self.db.add_user(user)
            user = await self.db.get_user(message.from_user.id)
            if not user.is_active:
                await message.answer(const.WELCOME_MESSAGE)
                return

            # Log the command activity
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {
                    "command": "/start",
                    "command_args": message.text.split()[1:]
                    if len(message.text.split()) > 1
                    else None,
                    "chat_type": message.chat.type,
                },
            )

            await message.answer(
                const.CHOOSE_PROJECT_MESSAGE.format(
                    first_name=message.from_user.first_name
                )
            )

            await self.db.update_user(user.user_id, current_session_id=None)

        except DatabaseError as e:
            self.logger.error(f"Database error in start command: {e}")
            await message.answer(const.REGISTRATION_ISSUE_MESSAGE)

    async def handle_id_command(self, message: Message):
        """
        /id command - Show user ID
        """
        try:
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {"command": "/id"},
            )
            await message.answer(
                f"Your user ID is: <code>{message.from_user.id}</code>",
                parse_mode="HTML",
            )
        except DatabaseError as e:
            self.logger.error(f"Database error in id command: {e}")
            await message.answer("❌ Unable to retrieve your user ID at the moment.")

    async def handle_help_command(self, message: Message):
        """
        /help command
        """
        try:
            # Get user for personalized response
            user = await self.db.get_user(message.from_user.id)

            # Log command
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {"command": "/help"},
            )

            help_text = (
                const.ADMIN_HELP + const.USER_HELP
                if user and user.user_role in (BotConstants.ROLE_SUPERADMIN,)
                else const.USER_HELP
            )

            await message.answer(help_text)

        except DatabaseError as e:
            self.logger.error(f"Database error in help command: {e}")
            await message.answer(const.HELP_ERROR)

    async def handle_stats_command(self, message: Message):
        """
        /stats command - Show bot/user statistics
        """
        is_admin = await self.db.is_admin_or_higher(message.from_user.id)
        try:
            # Check if user has permission

            user_id = message.text.split()[1] if len(message.text.split()) > 1 else None

            if is_admin and not user_id:
                # Get comprehensive bot analytics
                analytics = await self.db.get_bot_analytics(
                    days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )
                command_stats = await self.db.get_command_usage_stats(
                    days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )

                stats_text = const.STATISTICS_MESSAGE.format(
                    analytics_days=BotConstants.DEFAULT_ANALYTICS_DAYS,
                    total_active_users=analytics["total_active_users"],
                    new_users_period=analytics["new_users_period"],
                    active_users_period=analytics["active_users_period"],
                    activity_breakdown=chr(10).join(
                        [
                            f"• {key}: {value}"
                            for key, value in analytics["activity_breakdown"].items()
                        ]
                    ),
                    top_commands=chr(10).join(
                        [
                            f"• {key}: {value}"
                            for key, value in list(command_stats.items())[:5]
                        ]
                    ),
                )
            else:
                if not user_id or not is_admin:
                    user_id = message.from_user.id
                # Get user-specific stats
                user_stats = await self.db.get_user_activity_stats(
                    user_id, days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )
                total_tokens = sum(
                    [
                        item["activity_data"].get("total_tokens", 0)
                        for item in await self.db.get_message_activity_user_stats(
                            user_id
                        )
                    ]
                )
                stats_text = const.USER_STATS_MESSAGE.format(
                    analytics_days=BotConstants.DEFAULT_ANALYTICS_DAYS,
                    total_messages=user_stats["total_messages"],
                    total_commands=user_stats["total_commands"],
                    total_tokens=total_tokens,
                    first_interaction=user_stats["first_interaction"][:10]
                    if user_stats["first_interaction"]
                    else "Unknown",
                )

            # Log command usage
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {"command": "/stats"},
            )

            await message.answer(stats_text, parse_mode=None)

        except DatabaseError as e:
            self.logger.error(f"Database error in stats command: {e}")
            await message.answer(const.STATISTICS_ERROR)
            if is_admin:
                await message.answer(str(e))

    async def handle_admin_command(self, message: Message):
        """
        /admin command - Admin panel access
        """
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer(const.ADMIN_PRIVILEGES_ERROR)
                return

            # Get user counts by role
            superadmins = await self.db.get_users_by_role(BotConstants.ROLE_SUPERADMIN)
            users = await self.db.get_users_by_role(BotConstants.ROLE_USER)

            # Log admin panel access
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {"action": "panel_access", "command": "/admin"},
            )

            admin_text = const.ADMIN_PANEL_MESSAGE.format(
                superadmins=len(superadmins),
                users=len(users),
            )

            await message.answer(admin_text, parse_mode=None)

        except DatabaseError as e:
            self.logger.error(f"Database error in admin command: {e}")
            await message.answer(const.ADMIN_ERROR)

    async def handle_ban_command(self, message: Message):
        """
        /ban command - Ban a user
        """
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer(const.ADMIN_PRIVILEGES_ERROR)
                return

            # Parse command arguments
            args = message.text.split()[1:]
            if not args:
                await message.answer("Usage: /ban <user_id>")
                return

            try:
                target_user_id = int(args[0])
            except ValueError:
                await message.answer("❌ Invalid user ID")
                return

            # Check if you can manage this user
            can_manage = await self.db.can_manage_user(
                message.from_user.id, target_user_id
            )
            if not can_manage:
                await message.answer(
                    "❌ Cannot ban this user (insufficient permissions)"
                )
                return

            # Ban user (soft delete)
            success = await self.db.deactivate_user(target_user_id)

            # Log admin action
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {
                    "action": "ban_user",
                    "target_user_id": target_user_id,
                    "success": success,
                },
            )

            if success:
                await message.answer(f"✅ User {target_user_id} has been banned.")
            else:
                await message.answer(f"❌ Failed to ban user {target_user_id}")

        except DatabaseError as e:
            self.logger.error(f"Database error in ban command: {e}")
            await message.answer("❌ Unable to process ban command at the moment.")

    async def handle_list_users_command(self, message: Message):
        """
        /list_users command - List all users
        """
        users_limit: int = 100  # Limit to avoid overly long messages
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer("❌ Access denied.")
                return

            users: list[User] = await self.db.get_all_users()
            if not users:
                await message.answer("No users found.")
                return

            response_lines = ["👥 Registered Users:"]
            for user in users[:users_limit]:
                status = "✅" if user.is_active else "❌"
                username: str = f"@{user.username}" if user.username else ""
                response_lines.append(
                    f"• <code>{user.user_id}</code>, Name: {user.first_name} {user.last_name or ''} {username}, Role: {user.user_role}, Status: {status}"
                )

            # Log admin action
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {"action": "list_users", "total_users": len(users)},
            )

            # Send the response in chunks if too long
            response_text: str = "\n".join(response_lines)
            for i in range(0, len(response_text), MAX_MESSAGE_LENGTH):
                await message.answer(
                    remove_non_telegram_html(response_text[i : i + MAX_MESSAGE_LENGTH]),
                    parse_mode="HTML",
                )

        except DatabaseError as e:
            self.logger.error(f"Database error in list users command: {e}")
            await message.answer("❌ Unable to retrieve user list at the moment.")

    async def handle_activate_command(self, message: Message):
        """
        /activate command - Activate a user
        """
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer("❌ Access denied.")
                return

            # Parse command arguments
            args = message.text.split()[1:]
            if not args:
                await message.answer("Usage: /activate <user_id>")
                return

            try:
                target_user_id = int(args[0])
            except ValueError:
                await message.answer("❌ Invalid user ID")
                return

            # Check if you can manage this user
            can_manage = await self.db.can_manage_user(
                message.from_user.id, target_user_id
            )
            if not can_manage:
                await message.answer(
                    "❌ Cannot manage this user (insufficient permissions)"
                )
                return

            # Activate user
            success = await self.db.activate_user(target_user_id)

            # Log admin action
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {
                    "action": "activate_user",
                    "target_user_id": target_user_id,
                    "success": success,
                },
            )

            if success:
                await message.answer(f"✅ User {target_user_id} has been activated.")
                try:
                    await message.bot.send_message(
                        target_user_id, const.USER_ACTIVATION_MESSAGE
                    )
                    await message.bot.send_chat_action(
                        chat_id=message.from_user.id, action="upload_photo"
                    )
                except Exception as e:
                    self.logger.debug(
                        f"Failed to notify user {target_user_id} about activation: {e}"
                    )
            else:
                await message.answer(f"❌ Failed to activate user {target_user_id}")

        except DatabaseError as e:
            self.logger.error(f"Database error in activate command: {e}")
            await message.answer("❌ Unable to process activate command at the moment.")

    async def handle_promote_command(self, message: Message):
        """
        /promote command - Promote user to higher role
        """
        try:
            # Only superadmins can promote
            if not await self.db.is_superadmin(message.from_user.id):
                await message.answer("❌ Only superadmins can promote users.")
                return

            args = message.text.split()[1:]
            if len(args) < 2:
                await message.answer(
                    f"Usage: /promote <user_id> <role>\nRoles: {', '.join(BotConstants.VALID_ROLES)}"
                )
                return

            try:
                target_user_id = int(args[0])
                new_role = args[1].lower()
            except ValueError:
                await message.answer("❌ Invalid arguments")
                return

            # Validate role
            if new_role not in BotConstants.VALID_ROLES:
                await message.answer(
                    f"❌ Invalid role. Valid roles: {', '.join(BotConstants.VALID_ROLES)}"
                )
                return

            # Set new role
            success = await self.db.set_user_role(target_user_id, new_role)

            # Log promotion
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {
                    "action": "promote_user",
                    "target_user_id": target_user_id,
                    "new_role": new_role,
                    "success": success,
                },
            )

            if success:
                await message.answer(f"✅ User {target_user_id} promoted to {new_role}")
            else:
                await message.answer("❌ Failed to promote user")

        except DatabaseError as e:
            self.logger.error(f"Database error in promote command: {e}")
            await message.answer("❌ Unable to process promotion at the moment.")

    async def handle_settings_command(self, message: Message, state: FSMContext):
        """
        /settings command - User settings
        """
        try:
            # Get user current settings
            user = await self.db.get_user(message.from_user.id)
            if not user:
                await message.answer("❌ User not found. Please /start first.")
                return

            # Set FSM state
            await state.set_state(UserStates.in_settings)

            # Log settings access
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {"command": "/settings"},
            )

            settings_text = const.SETTINGS_MESSAGE.format(
                first_name=user.first_name,
                last_name=user.last_name or "",
                language=user.language_code or "Not set",
                role=user.user_role,
                total_messages=user.total_messages,
            )

            await message.answer(settings_text, parse_mode="Markdown")

        except DatabaseError as e:
            self.logger.error(f"Database error in settings command: {e}")
            await message.answer(const.SETTINGS_ERROR)

    async def handle_chat_command(self, message: Message, state: FSMContext):
        """Handle /chat <name> command to join an existing chat session"""
        try:
            # Get the session name from command arguments or use user's first name
            session_name: str | None = (
                message.text.split(maxsplit=1)[1]
                if len(message.text.split()) > 1
                else None
            )
            if not session_name:
                return await message.answer(
                    "Please provide a valid session name (1-100 characters)."
                )

            # Sanitize the session name
            if session_name and any(char in session_name for char in ["<", ">", "&"]):
                return await message.answer(
                    "Session name cannot contain <, >, or & characters."
                )

            # Check if a session with this name already exists for the user
            sessions = await self.db.list_chat_sessions(user_id=message.from_user.id)
            existing_session = next(
                (s for s in sessions if s.name == session_name), None
            )

            if existing_session:
                # Switch to existing session
                session_id = existing_session.session_id
                await message.answer(f"Joined existing chat session: {session_name}")
            else:
                return await message.answer(
                    f"No existing session named '{session_name}'. Please use /start to start a new chat."
                )

            # Update user's current session
            await self.db.update_user(
                user_id=message.from_user.id, current_session_id=session_id
            )
            # update session's last activity so it doesn't end immediately
            await self.db.update_chat_session_activity(session_id)

            # Reset FSM state to handle new chat messages
            await state.set_state()

        except Exception as e:
            self.logger.error(f"Error in handle_chat_command: {e}")
            await message.answer(const.REQUEST_ERROR)

    async def handle_select_project_command(self, message: Message, state: FSMContext):
        """Handle /project-name command to start a new chat session"""
        try:
            # Get the project name from command
            project_name: str | None = message.text.lstrip("/").strip()
            project_info: ProjectInfo = PROJECTS.get(project_name)
            if not project_info:
                return await message.answer(
                    "Please provide a valid project name. Available projects:\n"
                    + "\n".join(f"/{name}" for name in PROJECTS.keys())
                )
            # create a unique session name like "business_web_2025-10-05_14:31:23"
            session_name: str = (
                f"{project_name}_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}"
            )

            # Create new session
            session_id = ChatSessionManager().create_session(
                project_dir=project_info["project_dir"],
                collection_name=project_info["collection_name"],
                project_prompt=project_info.get("project_prompt"),
                repo_url=project_info.get("repo_url"),
                submodules=project_info.get("submodules"),
            )
            # save session to db
            await self.db.create_chat_session(
                user_id=message.from_user.id,
                session_id=session_id,
                name=session_name,
            )
            await message.answer(
                f"Created new chat session for <b>{project_name}</b>.\nWrite your question:",
                parse_mode="HTML",
            )

            # Update user's current session
            await self.db.update_user(
                user_id=message.from_user.id, current_session_id=session_id
            )

            # Reset FSM state to handle new chat messages
            await state.set_state()

        except Exception as e:
            self.logger.error(f"Error in handle_chat_command: {e}")
            await message.answer(const.REQUEST_ERROR)

    async def handle_end_chat_command(self, message: Message, state: FSMContext):
        """Handle /end_chat command to end the current chat session"""
        try:
            user: User | None = await self.db.get_user(message.from_user.id)
            if not user or not user.current_session_id:
                await message.answer(const.NO_ACTIVE_CHAT)
                return

            # Clear user's current session
            await self.db.update_user(
                user_id=message.from_user.id, current_session_id=None
            )

            await message.answer(const.CHAT_ENDED_MESSAGE)

            # Reset FSM state
            await state.set_state()

        except Exception as e:
            self.logger.error(f"Error in handle_end_chat_command: {e}")
            await message.answer(const.REQUEST_ERROR)

    async def handle_my_chats_command(self, message: Message, state: FSMContext):
        """Handle /my_chats command to list all chat sessions for the user"""
        try:
            # Get all chat sessions for the user
            sessions: list[ChatSession] = await self.db.list_chat_sessions(
                user_id=message.from_user.id
            )

            if not sessions:
                await message.answer(
                    "You don't have any chat sessions yet. Use /start to create one!"
                )
                return

            # Format sessions into a numbered list
            response = ["📋 Your chat sessions:"]
            for i, session in enumerate(sessions, 1):
                # Format the last activity time if available
                last_active = ""
                if session.last_activity:
                    last_active = f" (last active: {session.last_activity.strftime('%Y-%m-%d %H:%M')})"

                # Add session name and message count
                response.append(
                    f"{i}. <code>{session.name}</code>{last_active} - {session.message_count} messages"
                )
            if len(response) > 31:
                trimmed_number: int = len(response) - 31
                response = response[:31]
                response.append(f"... and {trimmed_number} more sessions.")

            # Add current session indicator if any
            user = await self.db.get_user(message.from_user.id)
            if user and user.current_session_id:
                current_session = next(
                    (s for s in sessions if s.session_id == user.current_session_id),
                    None,
                )
                if current_session:
                    response.append(f"\n💬 Current session: {current_session.name}.")

            response.append(
                "\nUse /chat (name) to join a session (just click a session name above to copy it)."
            )

            # Send the response
            await message.answer(
                remove_non_telegram_html("\n".join(response)), parse_mode="HTML"
            )

        except Exception as e:
            self.logger.error(f"Error listing chat sessions: {e}")
            await message.answer(const.REQUEST_ERROR)

    # ==================== FSM STATE HANDLERS ====================

    async def handle_name_input(self, message: Message, state: FSMContext):
        """
        Handle name input in FSM
        """
        # Clear state
        await state.clear()
        await message.answer("❌ You can't change your name!")

    # ==================== MESSAGE HANDLERS ====================

    @staticmethod
    async def handle_current_state(message: Message, state: FSMContext):
        """
        Handle any text message
        """
        # Check current FSM state
        current_state = await state.get_state()
        if not current_state:
            return False

        # Handle based on current FSM state
        if current_state == UserStates.in_settings.state:
            if message.text.lower() == "name":
                await message.answer("👤 Please enter your new name:")
                await state.set_state(UserStates.waiting_for_name)
            elif message.text.lower() == "done":
                await message.answer("✅ Settings updated! (no)")
                await state.clear()
            else:
                await message.answer(
                    "Please reply with 'name' to change your name or 'done' to finish."
                )
        else:
            return False
        return True

    async def handle_stop_command(self, message: Message, state: FSMContext):
        """Handle /stop command to stop ongoing response generation"""
        # get ongoing generation users from
        ongoing_generation: set[int] = self.cache.get(
            self.ONGOING_GENERATION_CACHE_KEY, set()
        )
        if message.from_user.id not in ongoing_generation:
            await message.answer("No ongoing response generation to stop.")
            return
        # Add user to stopped generation set
        stop_generation: set[int] = self.cache.setdefault(
            self.STOP_GENERATION_CACHE_KEY, set()
        )
        stop_generation.add(message.from_user.id)

    async def handle_chat_message(self, message: Message, state: FSMContext):
        """Handle chat messages with the AI agent"""
        if await self.handle_current_state(message, state):
            return

        user_id: int = message.from_user.id

        if user_id in self.cache.get(self.ONGOING_GENERATION_CACHE_KEY, set()):
            await message.answer(
                "⏳ Please wait, still generating a previous response..."
            )
            return

        try:
            # Check for active session
            user: User = await self.db.get_user(user_id)
            if not user or not user.current_session_id:
                await message.answer(const.NO_ACTIVE_CHAT)
                return

            try:
                session_manager: ChatSessionManager = ChatSessionManager(
                    session_id=user.current_session_id
                )
            except FileNotFoundError:
                await message.answer(
                    "Your chat session not found. Please use /chat (name) to create a new session."
                )
                await self.db.update_user(user_id=user_id, current_session_id=None)
                await self.db.soft_delete_chat_session(
                    user_id=user_id, session_id=user.current_session_id
                )
                return
            if not session_manager.active_session:
                await message.answer(
                    "Your don't have an active chat session. Please use /chat (name) to create a new session."
                )
                return

            self.cache.setdefault(self.ONGOING_GENERATION_CACHE_KEY, set()).add(user_id)
            self.cache.setdefault(self.STOP_GENERATION_CACHE_KEY, set()).discard(
                user_id
            )

            agent: ChatAgent = ChatAgent(
                project_dir=session_manager.project_dir,
                collection_name=session_manager.collection_name,
                session_manager=session_manager,
            )

            # Send typing action
            await message.bot.send_chat_action(chat_id=user_id, action="typing")

            # Process the message and get response
            meta_message: Message | None = None
            response: str = ""
            for output, response_type in agent.run(message.text):
                if user_id in self.cache.get(self.STOP_GENERATION_CACHE_KEY, set()):
                    await message.answer(const.GENERATION_STOPPED_MESSAGE)
                    self.cache[self.STOP_GENERATION_CACHE_KEY].discard(user_id)
                    session_manager.fix_messages_after_interruption()
                    return
                await message.bot.send_chat_action(chat_id=user_id, action="typing")
                if response_type == "partial":
                    # replace ":" in the end with "..." to indicate thinking
                    output = "...".join(output.rsplit(":", 1))

                    meta_message = await self._update_meta_message(
                        message, meta_message, output
                    )
                    await message.bot.send_chat_action(chat_id=user_id, action="typing")
                else:
                    response = output

            await self.db.update_chat_session_activity(
                user.current_session_id, len(agent.messages)
            )

            await message.answer(
                const.FORMATTING_RESPONSE_MESSAGE,
                parse_mode="HTML",
                disable_notification=True,
            )

            # Split long messages into chunks
            while response:
                await message.bot.send_chat_action(chat_id=user_id, action="typing")
                chunk: str = response[: MAX_MESSAGE_LENGTH - 400]
                response = response[MAX_MESSAGE_LENGTH - 400 :]
                await message.answer(
                    markdown_to_telegram_html_ai(chunk),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.1)  # Slight delay to avoid hitting rate limits
            await message.answer(
                const.RESPONSE_END_MESSAGE, parse_mode="HTML", disable_notification=True
            )

        except Exception as e:
            self.logger.error(f"Error handling chat message: {e}", exc_info=True)
            await message.answer(const.REQUEST_ERROR)
        else:
            # Log the message activity
            try:
                # Log user activity
                await self.db.log_activity(
                    user_id=user_id,
                    activity_type=BotConstants.ACTIVITY_MESSAGE,
                    activity_data={
                        "message_length": len(message.text or ""),
                        "response_length": len(output),
                        "tokens_used": agent.total_tokens if agent else None,
                    },
                    session_id=user.current_session_id,
                )
            except DatabaseError as e:
                self.logger.error(f"Database error logging message activity: {e}")
        finally:
            self.cache[self.ONGOING_GENERATION_CACHE_KEY].discard(user_id)

    @staticmethod
    async def _update_meta_message(
        current_message: Message, meta_message: Message | None, new_text: str
    ) -> Message:
        """Helper to update or send a meta message"""
        new_text = "<i>" + clean(new_text, tags=[], strip=True) + "</i>"
        if not meta_message:
            meta_message = await current_message.answer(
                f"<b>Thinking...</b>\n\n{new_text}",
                parse_mode="HTML",
                disable_notification=True,
            )
        else:
            # don't exceed max message length minus buffer for "Formatting response"
            if len(meta_message.text) + len(new_text) > MAX_MESSAGE_LENGTH - 40:
                if meta_message.text.endswith("..."):
                    if not len(meta_message.text) > MAX_MESSAGE_LENGTH - 40:
                        meta_message = await meta_message.edit_text(
                            meta_message.text + " ...", parse_mode="HTML"
                        )
                else:
                    meta_message = await meta_message.edit_text(
                        meta_message.text + "\n...", parse_mode="HTML"
                    )
            else:
                meta_message = await meta_message.edit_text(
                    "<i>" + meta_message.text + "</i>\n\n" + new_text, parse_mode="HTML"
                )
        return meta_message

    async def get_current_session_manager(
        self, user_id: int
    ) -> ChatSessionManager | None:
        """Helper to get current session manager for a user"""
        try:
            user: User | None = await self.db.get_user(user_id)
            if not user or not user.current_session_id:
                return None
            try:
                return ChatSessionManager(session_id=user.current_session_id)
            except FileNotFoundError:
                await self.db.update_user(user_id=user_id, current_session_id=None)
                return None
        except Exception as e:
            self.logger.error(f"Database error getting session manager: {e}")
            return None

    # Git commands
    async def handle_list_branches_command(self, message: Message):
        session_manager: (
            ChatSessionManager | None
        ) = await self.get_current_session_manager(message.from_user.id)
        if not session_manager:
            return await message.answer(const.NO_ACTIVE_CHAT)
        try:
            response: str = "List of branches: " + "\n".join(
                get_all_branches(session_manager.project_dir)
            )
            while response:
                chunk: str = response[:MAX_MESSAGE_LENGTH]
                response = response[MAX_MESSAGE_LENGTH:]
                await message.answer(chunk, parse_mode=None)
                await asyncio.sleep(0.1)
        except Exception as e:
            self.logger.error(
                f"Error handling list branches command: {e}", exc_info=True
            )
            await message.answer("List branches command error: " + str(e))

    async def handle_switch_branch_command(self, message: Message):
        session_manager: (
            ChatSessionManager | None
        ) = await self.get_current_session_manager(message.from_user.id)
        if not session_manager:
            return await message.answer(const.NO_ACTIVE_CHAT)
        try:
            new_branch_name = message.text.split(" ")[1]
            switch_branch(
                session_manager.collection_name,
                session_manager.project_dir,
                new_branch_name,
                session_manager.submodules,
            )
            await self.handle_current_branch_command(message)
        except Exception as e:
            self.logger.error(
                f"Error handling switch branch command: {e}", exc_info=True
            )
            await message.answer("Switch branch command error: " + str(e))

    async def handle_current_branch_command(self, message: Message):
        session_manager: (
            ChatSessionManager | None
        ) = await self.get_current_session_manager(message.from_user.id)
        if not session_manager:
            return await message.answer(const.NO_ACTIVE_CHAT)
        try:
            await message.answer(
                "Current branch:\n"
                + get_current_branch(
                    session_manager.project_dir, session_manager.submodules
                )
            )
        except Exception as e:
            self.logger.error(
                f"Error handling current branch command: {e}", exc_info=True
            )
            await message.answer("Current branch command error: " + str(e))

    async def handle_pull_current_branch_command(self, message: Message):
        session_manager: (
            ChatSessionManager | None
        ) = await self.get_current_session_manager(message.from_user.id)
        if not session_manager:
            return await message.answer(const.NO_ACTIVE_CHAT)
        try:
            pull_current_branch(
                session_manager.collection_name, session_manager.project_dir
            )
            await message.answer("Current branch pulled.")
        except Exception as e:
            self.logger.error(
                f"Error handling pull current branch command: {e}", exc_info=True
            )
            await message.answer("pull current branch command error: " + str(e))

    # ==================== CALLBACK HANDLERS ====================

    async def handle_any_callback(self, callback: CallbackQuery):
        """Handle any other callback"""
        try:
            await self.db.log_activity(
                callback.from_user.id,
                BotConstants.ACTIVITY_CALLBACK,
                {"callback_data": callback.data},
            )

            await callback.answer("Don't click buttons!")

        except DatabaseError as e:
            self.logger.error(f"Database error in callback handler: {e}")
            await callback.answer("Button clicked!")


class UserStates(StatesGroup):
    waiting_for_name = State()
    in_settings = State()
