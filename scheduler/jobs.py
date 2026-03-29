import logging
from datetime import datetime, timezone

from telegram.ext import CallbackContext

from agent.context_builder import build_context
from agent.groq_client import generate_response
from agent.prompt_builder import build_prompt
from config import settings
from db.queries import (
    create_checkin,
    get_active_projects,
    get_days_since_movement,
    get_user_state,
    log_event,
    update_checkin,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


# NOTE: _is_paused and other sync DB calls (get_user_state, log_event, etc.) are called
# directly on the event loop. For a single-user bot this is acceptable — DB round-trips
# are fast (<10ms on Railway→Supabase). If extended to multiple users, wrap in run_in_executor.
def _is_paused(user_id: int) -> bool:
    user = get_user_state(user_id)
    if user is None or user.pause_until is None:
        return False
    pause_until = user.pause_until
    if pause_until.tzinfo is None:
        pause_until = pause_until.replace(tzinfo=timezone.utc)
    return pause_until > datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------


async def morning_checkin_job(context: CallbackContext) -> None:
    user_id = settings.TELEGRAM_USER_ID
    try:
        if _is_paused(user_id):
            logger.info("morning_checkin_job: user is paused, skipping")
            return

        user = get_user_state(user_id)
        if user is None or user.conversation_state != "ACTIVE":
            logger.info("morning_checkin_job: user not in ACTIVE state, skipping")
            return

        checkin = create_checkin(user_id, "morning")
        if checkin is None:
            logger.info("morning_checkin_job: already sent today, skipping (dedup)")
            return

        ctx = await build_context(user_id)
        system_prompt, user_message = build_prompt("morning", ctx)
        response = await generate_response(system_prompt, user_message)

        await context.bot.send_message(chat_id=settings.TELEGRAM_USER_ID, text=response)
        update_checkin(checkin.id, bot_message=response, status="sent")
        log_event(user_id, "checkin_sent", {"type": "morning"})

    except Exception as exc:
        logger.error("morning_checkin_job failed: %s", exc, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=settings.TELEGRAM_USER_ID,
                text="Error interno en el check-in de la mañana. Revisa los logs.",
            )
        except Exception:
            logger.error("morning_checkin_job: also failed to send error message", exc_info=True)


async def midday_checkin_job(context: CallbackContext) -> None:
    user_id = settings.TELEGRAM_USER_ID
    try:
        if _is_paused(user_id):
            logger.info("midday_checkin_job: user is paused, skipping")
            return

        user = get_user_state(user_id)
        if user is None or user.conversation_state != "ACTIVE":
            logger.info("midday_checkin_job: user not in ACTIVE state, skipping")
            return

        checkin = create_checkin(user_id, "midday")
        if checkin is None:
            logger.info("midday_checkin_job: already sent today, skipping (dedup)")
            return

        ctx = await build_context(user_id)
        system_prompt, user_message = build_prompt("midday", ctx)
        response = await generate_response(system_prompt, user_message)

        await context.bot.send_message(chat_id=settings.TELEGRAM_USER_ID, text=response)
        update_checkin(checkin.id, bot_message=response, status="sent")
        log_event(user_id, "checkin_sent", {"type": "midday"})

    except Exception as exc:
        logger.error("midday_checkin_job failed: %s", exc, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=settings.TELEGRAM_USER_ID,
                text="Error interno en el check-in del mediodía. Revisa los logs.",
            )
        except Exception:
            logger.error("midday_checkin_job: also failed to send error message", exc_info=True)


async def evening_checkin_job(context: CallbackContext) -> None:
    user_id = settings.TELEGRAM_USER_ID
    try:
        if _is_paused(user_id):
            logger.info("evening_checkin_job: user is paused, skipping")
            return

        user = get_user_state(user_id)
        if user is None or user.conversation_state != "ACTIVE":
            logger.info("evening_checkin_job: user not in ACTIVE state, skipping")
            return

        checkin = create_checkin(user_id, "evening")
        if checkin is None:
            logger.info("evening_checkin_job: already sent today, skipping (dedup)")
            return

        ctx = await build_context(user_id)
        system_prompt, user_message = build_prompt("evening", ctx)
        response = await generate_response(system_prompt, user_message)

        await context.bot.send_message(chat_id=settings.TELEGRAM_USER_ID, text=response)
        update_checkin(checkin.id, bot_message=response, status="sent")
        log_event(user_id, "checkin_sent", {"type": "evening"})

    except Exception as exc:
        logger.error("evening_checkin_job failed: %s", exc, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=settings.TELEGRAM_USER_ID,
                text="Error interno en el check-in de la tarde. Revisa los logs.",
            )
        except Exception:
            logger.error("evening_checkin_job: also failed to send error message", exc_info=True)


async def weekly_retro_job(context: CallbackContext) -> None:
    user_id = settings.TELEGRAM_USER_ID
    try:
        if _is_paused(user_id):
            logger.info("weekly_retro_job: user is paused, skipping")
            return

        user = get_user_state(user_id)
        if user is None or user.conversation_state != "ACTIVE":
            logger.info("weekly_retro_job: user not in ACTIVE state, skipping")
            return

        checkin = create_checkin(user_id, "weekly")
        if checkin is None:
            logger.info("weekly_retro_job: already sent this week, skipping (dedup)")
            return

        ctx = await build_context(user_id)
        system_prompt, user_message = build_prompt("weekly", ctx)
        response = await generate_response(system_prompt, user_message)

        await context.bot.send_message(chat_id=settings.TELEGRAM_USER_ID, text=response)
        update_checkin(checkin.id, bot_message=response, status="sent")
        log_event(user_id, "checkin_sent", {"type": "weekly"})

    except Exception as exc:
        logger.error("weekly_retro_job failed: %s", exc, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=settings.TELEGRAM_USER_ID,
                text="Error interno en la retro semanal. Revisa los logs.",
            )
        except Exception:
            logger.error("weekly_retro_job: also failed to send error message", exc_info=True)


async def stagnation_check_job(context: CallbackContext) -> None:
    user_id = settings.TELEGRAM_USER_ID
    try:
        if _is_paused(user_id):
            logger.info("stagnation_check_job: user is paused, skipping")
            return

        user = get_user_state(user_id)
        if user is None or user.conversation_state != "ACTIVE":
            logger.info("stagnation_check_job: user not in ACTIVE state, skipping")
            return

        projects = get_active_projects(user_id)
        # Build context once outside the loop to avoid N redundant DB fetches
        ctx = await build_context(user_id)

        for proj in projects:
            try:
                days = get_days_since_movement(proj.id)
                if days is None or days <= 5:
                    continue

                # Inject the stagnant project as focus so the confrontation is project-specific
                ctx["focus_project"] = {
                    "id": proj.id,
                    "name": proj.name,
                    "days_since_movement": days,
                }
                system_prompt, user_message = build_prompt("confrontation", ctx)
                response = await generate_response(system_prompt, user_message)

                await context.bot.send_message(chat_id=settings.TELEGRAM_USER_ID, text=response)
                log_event(
                    user_id,
                    "stagnation_confrontation",
                    {"project_id": proj.id, "days": days},
                )

            except Exception as exc:
                logger.error(
                    "stagnation_check_job: error processing project %d: %s",
                    proj.id,
                    exc,
                    exc_info=True,
                )

    except Exception as exc:
        logger.error("stagnation_check_job failed: %s", exc, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=settings.TELEGRAM_USER_ID,
                text="Error interno en el chequeo de estancamiento. Revisa los logs.",
            )
        except Exception:
            logger.error(
                "stagnation_check_job: also failed to send error message", exc_info=True
            )
