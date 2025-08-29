import asyncio

from aiogram import Bot, Dispatcher

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
