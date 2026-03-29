import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from agent.context_builder import build_context
from bot.utils import check_user
from db.queries import create_user_state, get_user_state, set_pause, update_conversation_state

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    telegram_id = update.effective_chat.id

    try:
        user = get_user_state(telegram_id)

        if user is None:
            create_user_state(telegram_id)
            update_conversation_state(telegram_id, "ONBOARDING_IN_PROGRESS")
            await update.message.reply_text(
                "Bienvenido a Vantara. Soy tu agente de accountability personal.\n\n"
                "Vamos a empezar con el onboarding. Cuéntame: ¿en qué proyectos estás "
                "trabajando ahora mismo y cuál es el más prioritario?"
            )
        elif user.conversation_state == "ACTIVE":
            await update.message.reply_text(
                "Ya estás activo. Escríbeme cuando quieras o usa /status para ver tus proyectos."
            )
        else:
            await update.message.reply_text(
                "Hola de nuevo. Escríbeme para continuar."
            )

    except Exception as exc:
        logger.error("Error in /start for user %d: %s", telegram_id, exc, exc_info=True)
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    telegram_id = update.effective_chat.id

    try:
        ctx = await build_context(telegram_id)
        projects = ctx.get("projects", [])

        if not projects:
            await update.message.reply_text(
                "Aún no tienes proyectos. Escríbeme para empezar el onboarding."
            )
            return

        lines = []
        for p in projects:
            days = p.get("days_since_movement")
            if days is None:
                days_str = "sin actividad registrada"
            elif days == 0:
                days_str = "activo hoy"
            elif days == 1:
                days_str = "activo ayer"
            else:
                days_str = f"{days} días sin movimiento"

            lines.append(f"[P{p['priority']}] {p['name']} — {days_str}")
            if p.get("next_action"):
                lines.append(f"Next: {p['next_action']}")
            lines.append("")

        # Strip trailing blank line
        while lines and lines[-1] == "":
            lines.pop()

        await update.message.reply_text("\n".join(lines))

    except Exception as exc:
        logger.error("Error in /status for user %d: %s", telegram_id, exc, exc_info=True)
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    telegram_id = update.effective_chat.id

    try:
        # Parse argument — default 1 day
        args = context.args or []
        raw = args[0] if args else "1"

        try:
            days = int(raw)
        except ValueError:
            await update.message.reply_text(
                "Uso: /pause [días]. Ejemplo: /pause 3 (o /pause 0 para cancelar la pausa)."
            )
            return

        if days == 0:
            set_pause(telegram_id, None)
            await update.message.reply_text("Pausa cancelada. Retomando seguimiento.")
        else:
            pause_until = datetime.now(tz=timezone.utc) + timedelta(days=days)
            set_pause(telegram_id, pause_until)
            resume_date = pause_until.strftime("%d/%m/%Y")
            day_word = "día" if days == 1 else "días"
            await update.message.reply_text(
                f"Pausado por {days} {day_word}. Retomo el {resume_date}."
            )

    except Exception as exc:
        logger.error("Error in /pause for user %d: %s", telegram_id, exc, exc_info=True)
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    try:
        await update.message.reply_text("Motor de desbloqueo próximamente.")
    except Exception as exc:
        logger.error(
            "Error in /unblock for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def delegate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    try:
        await update.message.reply_text("Flujo de delegación próximamente.")
    except Exception as exc:
        logger.error(
            "Error in /delegate for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")
