import asyncio
import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.commands import (
    delegate_command,
    pause_command,
    start_command,
    status_command,
    unblock_command,
)
from bot.handlers import handle_text_message, handle_voice_message
from config import settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def main() -> None:
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("unblock", unblock_command))
    app.add_handler(CommandHandler("delegate", delegate_command))

    # Register message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Jobs will be registered in Phase 3

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
