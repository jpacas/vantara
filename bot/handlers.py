import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from agent.context_builder import build_context
from agent.groq_client import generate_response
from agent.prompt_builder import build_prompt
from bot.utils import check_user
from bot.voice import transcribe_voice

logger = logging.getLogger(__name__)


async def _dispatch_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """
    Core dispatch logic shared by text and voice message handlers.
    Reads conversation state and routes to the appropriate handler.
    """
    telegram_id = update.effective_chat.id

    try:
        ctx = await build_context(telegram_id)
    except Exception as exc:
        logger.error("DB error building context for user %d: %s", telegram_id, exc, exc_info=True)
        await update.message.reply_text(
            "Tuve un problema con la base de datos. Intento de nuevo en un momento."
        )
        return

    conversation_state = ctx.get("user_state", {}).get("conversation_state", "")

    if conversation_state == "ONBOARDING_PENDING":
        await update.message.reply_text("Usa /start para comenzar.")

    elif conversation_state == "ONBOARDING_IN_PROGRESS":
        await handle_onboarding_message(update, context, ctx, text)

    elif conversation_state == "ACTIVE":
        await handle_active_message(update, context, ctx, text)

    elif conversation_state == "PAUSED":
        await update.message.reply_text("Estás en pausa. Usa /pause 0 para retomar.")

    else:
        await update.message.reply_text("Estado desconocido. Usa /start.")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    text = update.message.text or ""
    await _dispatch_message(update, context, text)


async def handle_onboarding_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: dict,
    text: str,
) -> None:
    """Forward message to LLM using the onboarding prompt."""
    try:
        system_prompt, user_message_template = build_prompt("onboarding", ctx)
        # Append the actual user text to the template-generated user message
        combined_user_message = f"{user_message_template}\n\nUsuario: {text}"
        reply = await generate_response(system_prompt, combined_user_message)
        await update.message.reply_text(reply)
    except FileNotFoundError as exc:
        logger.error("Prompt template missing: %s", exc)
        await update.message.reply_text(
            "Tuve un problema con la configuración del agente. Intenta de nuevo."
        )
    except Exception as exc:
        logger.error(
            "Error in onboarding handler for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def handle_active_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: dict,
    text: str,
) -> None:
    """Forward message to LLM using the morning prompt (default mode for Phase 1)."""
    try:
        system_prompt, user_message_template = build_prompt("morning", ctx)
        combined_user_message = f"{user_message_template}\n\nUsuario: {text}"
        reply = await generate_response(system_prompt, combined_user_message)
        await update.message.reply_text(reply)
    except FileNotFoundError as exc:
        logger.error("Prompt template missing: %s", exc)
        await update.message.reply_text(
            "Tuve un problema con la configuración del agente. Intenta de nuevo."
        )
    except Exception as exc:
        logger.error(
            "Error in active handler for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_user(update):
        return

    voice = update.message.voice
    file_id = voice.file_id
    file_path = f"/tmp/voice_{file_id}.ogg"

    try:
        # Check file size before downloading (voice.file_size is in bytes)
        if voice.file_size and voice.file_size > 25 * 1024 * 1024:
            await update.message.reply_text(
                "El audio es muy largo. Por favor escribe tu mensaje."
            )
            return

        # Download voice file
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(file_path)

        # Double-check size on disk after download
        if os.path.exists(file_path) and os.path.getsize(file_path) > 25 * 1024 * 1024:
            await update.message.reply_text(
                "El audio es muy largo. Por favor escribe tu mensaje."
            )
            return

        # Transcribe
        transcribed_text = await transcribe_voice(file_path)

        if transcribed_text is None:
            await update.message.reply_text(
                "No pude transcribir el audio. Por favor escribe tu mensaje."
            )
            return

        # Dispatch as if it were a text message
        await _dispatch_message(update, context, transcribed_text)

    except Exception as exc:
        logger.error(
            "Error handling voice message for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")

    finally:
        # Always clean up temp file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as exc:
                logger.warning("Could not remove temp voice file %s: %s", file_path, exc)
