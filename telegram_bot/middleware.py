import logging
from datetime import datetime
from typing import Callable, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from telegram_bot.db import AsyncUserDatabase, create_user_from_telegram


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
                            if (
                                hasattr(event.message, "text")
                                and event.message.text == "/start"
                            ):
                                # For /start commands, reply with a more detailed message
                                await event.message.answer(
                                    "⚠️Welcome! Your access to this bot is not approved yet.\n"
                                    "Please contact the administrator for more information."
                                )
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
