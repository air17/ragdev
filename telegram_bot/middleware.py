import logging
from datetime import datetime
from typing import Callable, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

from telegram_bot.db import AsyncUserDatabase, create_user_from_telegram, UserRole, User


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to automatically handle user registration, activity tracking, and access control"""

    def __init__(
        self,
        db: AsyncUserDatabase,
        inactive_user_commands: set[str] | None = None,
        user_role_commands: set[str] | None = None,
    ):
        """
        Initialize the middleware with database and command permissions.

        Args:
            db: The async user database instance
            inactive_user_commands: Set of commands available to inactive users (e.g., {'/start', '/help'})
            user_role_commands: Set of commands available to users with 'user' role (e.g., {'/start', '/help', '/profile'})
                               Users with 'superadmin' role have access to all commands
        """
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

        # Default commands for inactive users (minimal set)
        self.inactive_user_commands = inactive_user_commands or {"/start"}

        # Default commands for regular users
        self.user_role_commands = user_role_commands or {"/start", "/help"}

        super().__init__()

    def _extract_command(self, event: TelegramObject) -> str | None:
        """Extract command from the event if it's a command message"""
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            # Extract the command (first word, including the /)
            command = event.text.split()[0].split("@")[
                0
            ]  # Remove bot username if present
            return command
        return None

    async def _check_command_allowed(
        self, user_id: int, command: str, db_user: User
    ) -> bool:
        """
        Check if user has permission to execute the command.

        Returns:
            True if user can execute the command, False otherwise
        """
        # If not a command, allow (this middleware only controls commands)
        if not command:
            return True

        # Check if user is inactive first
        if not db_user.is_active:
            # Inactive users can only use limited commands
            return command in self.inactive_user_commands

        # Superadmins have access to all commands
        if db_user.user_role == UserRole.SUPERADMIN.role_name:
            return True

        # Regular users have access to their allowed commands
        if db_user.user_role == UserRole.USER.role_name:
            return command in self.user_role_commands

        # Unknown role - deny by default
        self.logger.warning(f"Unknown role '{db_user.user_role}' for user {user_id}")
        return False

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

                # Fetch user from database to check status and role
                db_user: User | None = None
                try:
                    db_user = await self.db.get_user(user.id)
                except Exception:
                    self.logger.exception(
                        "Failed to fetch user from DB (treating as active): %s",
                        getattr(user, "id", None),
                    )

                # Extract command from the event
                command = self._extract_command(event)

                # Check command permissions
                if command and db_user:
                    has_permission = await self._check_command_allowed(
                        user.id, command, db_user
                    )

                    if not has_permission:
                        self.logger.info(
                            "User %s (role: %s, active: %s) denied access to command: %s",
                            user.id,
                            getattr(db_user, "role", "unknown"),
                            getattr(db_user, "is_active", False),
                            command,
                        )

                        # Send permission denied message
                        if isinstance(event, Message):
                            try:
                                await event.answer(
                                    "❌ You don't have permission to use this command."
                                )
                            except Exception:
                                self.logger.debug(
                                    "Failed to send permission denied message",
                                    exc_info=True,
                                )

                        # Stop processing
                        return None

                # Special handling for inactive users (for non-command messages)
                if db_user and not getattr(db_user, "is_active", True) and not command:
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
                                "❌ Your access to this bot is not approved."
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
