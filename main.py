import logging
from datetime import time as dtime

import pytz
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.commands import delegate_command, pause_command, start_command, status_command, unblock_command
from bot.handlers import handle_text_message, handle_voice_message
from config import settings
from scheduler.jobs import (
    evening_checkin_job,
    midday_checkin_job,
    morning_checkin_job,
    stagnation_check_job,
    weekly_retro_job,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def main() -> None:
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("unblock", unblock_command))
    app.add_handler(CommandHandler("delegate", delegate_command))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Register scheduled jobs
    job_queue = app.job_queue

    tz = pytz.timezone("America/Bogota")  # UTC-5 — adjust to user's timezone

    job_queue.run_daily(morning_checkin_job, time=dtime(8, 0, tzinfo=tz))
    job_queue.run_daily(midday_checkin_job, time=dtime(13, 0, tzinfo=tz))
    job_queue.run_daily(evening_checkin_job, time=dtime(19, 0, tzinfo=tz))
    job_queue.run_daily(weekly_retro_job, time=dtime(20, 0, tzinfo=tz), days=(4,))  # 4 = Friday
    job_queue.run_daily(stagnation_check_job, time=dtime(21, 0, tzinfo=tz))

    logger.info("Starting Vantara bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
