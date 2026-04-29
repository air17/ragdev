import asyncio
import functools
import logging

import bleach
from aiogram import Bot

from chat.sessions import ChatSessionManager
from project_management.const import PROJECTS
from project_management.git_utils import pull_current_branch
from telegram_bot import const
from telegram_bot.const import BotConstants
from telegram_bot.db import AsyncUserDatabase

MINUTES_TO_END_SESSIONS = 30

logger = logging.getLogger(__name__)


async def end_inactive_sessions_task(
    db: AsyncUserDatabase, bot: Bot, minutes: int = MINUTES_TO_END_SESSIONS
) -> None:
    """End chat sessions that have been inactive for a specified number of days.

    This function checks for chat sessions that have not had any activity for the given number of minutes,
    ends those sessions, and notifies the respective users via the Telegram bot.

    Parameters
    ----------
    db : Database
        The database instance to use for querying and updating sessions.
    bot : Bot
        The Telegram bot instance to send notifications.
    minutes : int
        The number of minutes of inactivity after which sessions should be ended.
    """
    user_ids: list[int] = await db.deactivate_old_current_sessions(minutes=minutes)
    for user_id in user_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=const.SESSION_EXPIRED_MESSAGE,
                disable_notification=True,
            )
        except Exception as e:
            logger.info(f"Error sending inactivity message to user {user_id}: {e}")


async def clear_empty_sessions_task(db: AsyncUserDatabase) -> None:
    """Clear empty chat sessions from the database and file system.

    db : Database
        The database instance to use for querying and deleting empty sessions.
    """
    session_ids: list[str] = await db.delete_empty_chat_sessions(days=1)
    for session_id in session_ids:
        try:
            ChatSessionManager.delete_session(session_id)
        except Exception as e:
            logger.error(f"Error deleting empty session {session_id}: {e}")


async def _notify_admins(bot: Bot, db: AsyncUserDatabase, text: str) -> None:
    """Send a message to all superadmin users. Errors are logged and swallowed."""
    try:
        admins = await db.get_users_by_role(BotConstants.ROLE_SUPERADMIN)
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.user_id, text=text, parse_mode="HTML"
                )
            except Exception as notify_err:
                logger.warning(f"Failed to notify admin {admin.user_id}: {notify_err}")
    except Exception as e:
        logger.error(f"Failed to fetch admins for notification: {e}")


async def pull_all_repos_task(bot: Bot, db: AsyncUserDatabase) -> None:
    """Pull the current branch for every configured project every 3 hours.

    Projects whose ``project_dir`` is empty or falsy are silently skipped.
    On per-project failure all superadmins are notified via the bot.
    """
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    for slug, project in PROJECTS.items():
        project_dir: str = project["project_dir"]
        if not project_dir:
            logger.debug(f"Skipping auto-pull for {slug}: project_dir not configured.")
            continue
        try:
            await loop.run_in_executor(
                None,
                functools.partial(
                    pull_current_branch, project_dir, project["submodules"]
                ),
            )
            logger.info(f"Auto-pull succeeded for {slug}.")
        except Exception as e:
            logger.error(f"Auto-pull failed for {slug}: {e}", exc_info=True)
            project_name: str = bleach.clean(project["name"], tags=set(), strip=False)
            short_error: str = bleach.clean(str(e)[:200], tags=set(), strip=False)
            await _notify_admins(
                bot,
                db,
                const.AUTO_PULL_FAILED_MESSAGE.format(
                    project_name=project_name, error=short_error
                ),
            )
