import asyncio
import uuid
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Callable, Any, Awaitable

import config
from telegram_bot.db import create_user_from_telegram, AsyncUserDatabase, DatabaseError


# Constants
class BotConstants:
    """Constants for bot operations"""

    # User roles
    ROLE_USER = "user"
    ROLE_SUPERADMIN = "superadmin"

    VALID_ROLES = [ROLE_USER, ROLE_SUPERADMIN]

    # User states (since FSM states are separate from DB user states)
    USER_STATE_SETTINGS = "in_settings"
    USER_STATE_WAITING_NAME = "waiting_for_name"

    # Activity types
    ACTIVITY_COMMAND = "command"
    ACTIVITY_MESSAGE = "message"
    ACTIVITY_CALLBACK = "callback"
    ACTIVITY_ADMIN_ACTION = "admin_action"
    ACTIVITY_PROFILE_UPDATE = "profile_update"
    ACTIVITY_INLINE_QUERY = "inline_query"
    ACTIVITY_CHAT_MEMBER_UPDATE = "chat_member_update"
    ACTIVITY_JOIN_REQUEST = "join_request"
    ACTIVITY_WEBHOOK_RECEIVED = "webhook_received"

    # Default values
    DEFAULT_ANALYTICS_DAYS = 30
    DEFAULT_CLEANUP_DAYS = 90
    DEFAULT_MESSAGE_TRUNCATE_LENGTH = 100


# Example FSM states
class UserStates(StatesGroup):
    waiting_for_name = State()
    in_settings = State()


class BotEventHandler:
    """Example class showing database method calls for different Telegram events"""

    def __init__(self, db: AsyncUserDatabase):
        self.db: AsyncUserDatabase = db
        self.router: Router = Router()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all event handlers"""
        # Message handlers
        self.router.message.register(self.handle_start_command, CommandStart())
        self.router.message.register(self.handle_help_command, Command("help"))
        self.router.message.register(self.handle_stats_command, Command("stats"))
        self.router.message.register(self.handle_admin_command, Command("admin"))
        self.router.message.register(self.handle_ban_command, Command("ban"))
        self.router.message.register(self.handle_activate_command, Command("activate"))
        self.router.message.register(self.handle_promote_command, Command("promote"))
        self.router.message.register(self.handle_settings_command, Command("settings"))

        # FSM handlers
        self.router.message.register(
            self.handle_name_input, UserStates.waiting_for_name
        )

        # General message handler (should be last)
        self.router.message.register(self.handle_any_message)

        # Callback query handlers
        self.router.callback_query.register(
            self.handle_settings_callback, F.data.startswith("settings_")
        )
        self.router.callback_query.register(
            self.handle_admin_callback, F.data.startswith("admin_")
        )
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
        session_id = str(uuid.uuid4())

        try:
            # Register user if new (will ignore if exists)
            await self.db.add_user(user)

            # Start user session
            await self.db.start_user_session(message.from_user.id, session_id)

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
                session_id,
            )

            await message.answer(
                f"👋 Welcome {message.from_user.first_name}! I'm your bot assistant."
            )

        except DatabaseError as e:
            self.logger.error(f"Database error in start command: {e}")
            await message.answer(
                "⚠️ Welcome! There was a minor issue with registration, but you can continue using the bot."
            )

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

            if user and user.user_role in (BotConstants.ROLE_SUPERADMIN,):
                help_text = (
                    "🔧 Admin Help:\n"
                    "/stats - Bot statistics\n"
                    "/admin - Admin panel\n"
                    "/ban - Ban user\n"
                    "/activate - Activate user\n"
                    "/promote - Promote user"
                    "/settings - Your settings\n"
                    "/help - This help message"
                )
            else:
                help_text = (
                    "📚 User Help:\n"
                    "/settings - Your settings\n"
                    "/help - This help message"
                )

            await message.answer(help_text)

        except DatabaseError as e:
            self.logger.error(f"Database error in help command: {e}")
            await message.answer(
                "📚 Basic Help:\n/settings - Your settings\n/help - This help message"
            )

    async def handle_stats_command(self, message: Message):
        """
        /stats command - Show bot/user statistics
        """
        try:
            # Check if user has permission
            is_admin = await self.db.is_admin_or_higher(message.from_user.id)

            if is_admin:
                # Get comprehensive bot analytics
                analytics = await self.db.get_bot_analytics(
                    days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )
                command_stats = await self.db.get_command_usage_stats(
                    days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )

                stats_text = f"""📊 Bot Statistics ({BotConstants.DEFAULT_ANALYTICS_DAYS} days)
👥 Total Active Users: {analytics["total_active_users"]}
🆕 New Users: {analytics["new_users_period"]}
🔥 Active in Period: {analytics["active_users_period"]}

📈 Activity Breakdown:
{chr(10).join([f"• {k}: {v}" for k, v in analytics["activity_breakdown"].items()])}

🎯 Top Commands:
{chr(10).join([f"• {k}: {v}" for k, v in list(command_stats.items())[:5]])}"""
            else:
                # Get user-specific stats
                user_stats = await self.db.get_user_activity_stats(
                    message.from_user.id, days=BotConstants.DEFAULT_ANALYTICS_DAYS
                )
                stats_text = f"""📊 Your Statistics ({BotConstants.DEFAULT_ANALYTICS_DAYS} days)
💬 Messages: {user_stats["total_messages"]}
⚡ Commands: {user_stats["total_commands"]}
📅 Member Since: {user_stats["first_interaction"][:10] if user_stats["first_interaction"] else "Unknown"}"""

            # Log command usage
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_COMMAND,
                {"command": "/stats"},
            )

            await message.answer(stats_text, parse_mode=None)

        except DatabaseError as e:
            self.logger.error(f"Database error in stats command: {e}")
            await message.answer("❌ Unable to retrieve statistics at the moment.")

    async def handle_admin_command(self, message: Message):
        """
        /admin command - Admin panel access
        """
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer("❌ Access denied. Admin privileges required.")
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

            admin_text = f"""🛡️ **Admin Panel**
👑 Superadmins: {len(superadmins)}
👤 Users: {len(users)}

Use /ban <user_id> to ban users
Use /activate <user_id> to activate users
Use /promote <user_id> <role> to promote users"""

            await message.answer(admin_text, parse_mode="Markdown")

        except DatabaseError as e:
            self.logger.error(f"Database error in admin command: {e}")
            await message.answer("❌ Unable to access admin panel at the moment.")

    async def handle_ban_command(self, message: Message):
        """
        /ban command - Ban a user
        """
        try:
            # Check admin permissions
            if not await self.db.is_admin_or_higher(message.from_user.id):
                await message.answer("❌ Access denied.")
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

            settings_text = f"""⚙️ **Your Settings**
👤 Name: {user.first_name} {user.last_name or ""}
🌐 Language: {user.language_code or "Not set"}
🎭 Role: {user.user_role}
📊 Total Messages: {user.total_messages}

Reply with 'name' to change your name
Reply with 'done' to finish"""

            await message.answer(settings_text, parse_mode="Markdown")

        except DatabaseError as e:
            self.logger.error(f"Database error in settings command: {e}")
            await message.answer("❌ Unable to load settings at the moment.")

    # ==================== FSM STATE HANDLERS ====================

    async def handle_name_input(self, message: Message, state: FSMContext):
        """
        Handle name input in FSM
        """
        try:
            new_name = message.text.strip()

            # Update user's first name
            success = await self.db.update_user(
                message.from_user.id, first_name=new_name
            )

            # Log the update
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_PROFILE_UPDATE,
                {"field": "first_name", "new_value": new_name, "success": success},
            )

            # Clear state
            await state.clear()

            if success:
                await message.answer(f"✅ Name updated to: {new_name}")
            else:
                await message.answer("❌ Failed to update name")

        except DatabaseError as e:
            self.logger.error(f"Database error in name input: {e}")
            await message.answer("❌ Failed to update name")
            await state.clear()

    # ==================== MESSAGE HANDLERS ====================

    async def handle_any_message(self, message: Message, state: FSMContext):
        """
        Handle any text message
        """
        try:
            # Auto-register user if not exists
            user = create_user_from_telegram(message.from_user)
            await self.db.add_user(user)

            # Check current FSM state
            current_state = await state.get_state()

            # Log message activity
            await self.db.log_activity(
                message.from_user.id,
                BotConstants.ACTIVITY_MESSAGE,
                {
                    "text_length": len(message.text) if message.text else 0,
                    "chat_type": message.chat.type,
                    "has_entities": bool(message.entities),
                    "fsm_state": current_state,
                },
            )

            # Handle based on current FSM state
            if current_state == UserStates.in_settings.state:
                if message.text.lower() == "name":
                    await message.answer("👤 Please enter your new name:")
                    await state.set_state(UserStates.waiting_for_name)
                elif message.text.lower() == "done":
                    await message.answer("✅ Settings updated!")
                    await state.clear()
                else:
                    await message.answer(
                        "Please reply with 'name' to change your name or 'done' to finish."
                    )
            else:
                # Regular message processing
                await message.answer("📝 I received your message!")

        except DatabaseError as e:
            self.logger.error(f"Database error in message handler: {e}")
            await message.answer("📝 I received your message!")

    # ==================== CALLBACK HANDLERS ====================

    async def handle_settings_callback(self, callback: CallbackQuery):
        """
        Handle settings-related callbacks
        """
        try:
            action = callback.data.replace("settings_", "")

            # Log callback activity
            await self.db.log_activity(
                callback.from_user.id,
                BotConstants.ACTIVITY_CALLBACK,
                {"callback_data": callback.data, "action": action},
            )

            if action == "notifications_on":
                user = await self.db.get_user(callback.from_user.id)
                settings = user.settings or {} if user else {}
                settings["notifications"] = True

                await self.db.update_user(callback.from_user.id, settings=settings)
                await callback.answer("🔔 Notifications enabled!")

            elif action == "notifications_off":
                user = await self.db.get_user(callback.from_user.id)
                settings = user.settings or {} if user else {}
                settings["notifications"] = False

                await self.db.update_user(callback.from_user.id, settings=settings)
                await callback.answer("🔕 Notifications disabled!")

            await callback.message.edit_text("⚙️ Settings updated!")

        except DatabaseError as e:
            self.logger.error(f"Database error in settings callback: {e}")
            await callback.answer("❌ Unable to update settings")

    async def handle_admin_callback(self, callback: CallbackQuery):
        """Handle admin panel callbacks"""
        try:
            if not await self.db.is_admin_or_higher(callback.from_user.id):
                await callback.answer("❌ Access denied", show_alert=True)
                return

            action = callback.data.replace("admin_", "")

            # Log admin callback
            await self.db.log_activity(
                callback.from_user.id,
                BotConstants.ACTIVITY_ADMIN_ACTION,
                {"action": f"callback_{action}", "callback_data": callback.data},
            )

            await callback.answer(f"Admin action: {action}")

        except DatabaseError as e:
            self.logger.error(f"Database error in admin callback: {e}")
            await callback.answer("❌ Error processing admin action")

    async def handle_any_callback(self, callback: CallbackQuery):
        """Handle any other callback"""
        try:
            await self.db.log_activity(
                callback.from_user.id,
                BotConstants.ACTIVITY_CALLBACK,
                {"callback_data": callback.data},
            )

            await callback.answer("Button clicked!")

        except DatabaseError as e:
            self.logger.error(f"Database error in callback handler: {e}")
            await callback.answer("Button clicked!")


# ==================== MIDDLEWARE ====================


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to automatically handle user registration, activity tracking, and access control"""

    def __init__(self, db: AsyncUserDatabase):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Middleware that runs before every handler
        """
        try:
            # Extract user from different event types
            user = None
            if hasattr(event, "from_user") and event.from_user:
                user = event.from_user
            elif hasattr(event, "new_chat_member") and event.new_chat_member:
                # new_chat_member may be an object with .user or a direct user-like object
                ncm = event.new_chat_member
                user = getattr(ncm, "user", ncm)

            if user and not getattr(user, "is_bot", False):
                # Auto-register user (best-effort)
                try:
                    user_obj = create_user_from_telegram(user)
                    await self.db.add_user(user_obj)
                except Exception:
                    # Don't fail the whole middleware on DB/write errors
                    self.logger.exception(
                        "Failed to add user to DB (continuing): %s",
                        getattr(user, "id", None),
                    )

                # Check if user is active (banned users are set to is_active=False)
                db_user = None
                try:
                    db_user = await self.db.get_user(user.id)
                except Exception:
                    self.logger.exception(
                        "Failed to fetch user from DB (treating as active): %s",
                        getattr(user, "id", None),
                    )

                if db_user and not getattr(db_user, "is_active", True):
                    self.logger.info(
                        "Blocked inactive user %s from accessing bot", user.id
                    )

                    # Try to notify the user (best-effort; swallow errors)
                    sent = False
                    if hasattr(event, "answer") and callable(getattr(event, "answer")):
                        try:
                            await event.answer(
                                "❌ Your access to this bot has been restricted."
                            )
                            sent = True
                        except Exception:
                            self.logger.debug(
                                "Failed to send restriction message via event.answer",
                                exc_info=True,
                            )

                    if (
                        not sent
                        and hasattr(event, "message")
                        and hasattr(event.message, "answer")
                    ):
                        try:
                            await event.message.answer(
                                "❌ Your access to this bot has been restricted."
                            )
                        except Exception:
                            self.logger.debug(
                                "Failed to send restriction message via event.message.answer",
                                exc_info=True,
                            )

                    # Stop processing for blocked users
                    return None

                # Update last seen (best-effort)
                try:
                    await self.db.update_user(
                        user.id, last_seen=datetime.now().isoformat()
                    )
                except Exception:
                    self.logger.exception(
                        "Failed to update user's last_seen (continuing): %s",
                        getattr(user, "id", None),
                    )

                # Add database to handler data for convenience
                data["db"] = self.db

        except Exception:
            # If middleware crashes unexpectedly, log and continue to handler (fail-open)
            self.logger.exception(
                "Unhandled exception in middleware (continuing to handler)"
            )

        # Continue to handler
        return await handler(event, data)


# ==================== COMPLETE USAGE EXAMPLE ====================


async def setup_production_bot():
    """Complete production bot setup with all features"""

    # Initialize database
    db = AsyncUserDatabase("production_bot.db")
    await db.initialize()

    # Initialize bot and dispatcher
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Add middleware for auto-registration
    dp.message.middleware(DatabaseMiddleware(db))
    dp.callback_query.middleware(DatabaseMiddleware(db))
    dp.inline_query.middleware(DatabaseMiddleware(db))

    # Setup event handlers
    event_handler = BotEventHandler(db)
    dp.include_router(event_handler.router)

    # Setup graceful shutdown
    async def on_shutdown():
        print("🛑 Shutting down bot...")
        await db.cleanup_old_activities(days=90)  # Final cleanup

    # Register shutdown handler
    dp.shutdown.register(on_shutdown)

    print("🚀 Bot starting...")

    # Start polling
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        await on_shutdown()


if __name__ == "__main__":
    # Run the production bot
    asyncio.run(setup_production_bot())
