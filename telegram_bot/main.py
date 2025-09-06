import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

import config
from telegram_bot.const import BotConstants
from telegram_bot.db import (
    AsyncUserDatabase,
)
from telegram_bot.event_handler import BotEventHandler
from telegram_bot.middleware import DatabaseMiddleware


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

    # Setup all available commands
    all_commands: list[BotCommand] = [
        BotCommand(command="/start", description="Start a new chat session"),
        BotCommand(command="/help", description="Show help information"),
        BotCommand(command="/my_chats", description="List all your chat sessions"),
        BotCommand(command="/end_chat", description="End the current chat session"),
        BotCommand(command="/list_branches", description="List all branches"),
        BotCommand(command="/current_branch", description="Show current branch"),
        BotCommand(command="/pull_current_branch", description="Pull current branch"),
        BotCommand(command="/settings", description="Your settings"),
        BotCommand(command="/admin", description="Admin panel"),
    ]
    await bot.set_my_commands(all_commands)

    # Setup graceful shutdown
    async def on_shutdown():
        print("🛑 Shutting down bot...")
        await db.cleanup_old_activities(
            days=BotConstants.DEFAULT_CLEANUP_DAYS
        )  # Final cleanup

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
