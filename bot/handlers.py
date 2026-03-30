import json as _json
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


_ONBOARDING_COMPLETE_MARKER = "[ONBOARDING_COMPLETO]"


async def handle_onboarding_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: dict,
    text: str,
) -> None:
    """
    Multi-turn onboarding handler.
    Tracks full conversation history in context.user_data.
    Detects [ONBOARDING_COMPLETO] marker and saves projects to DB.
    """
    telegram_id = update.effective_chat.id

    # Initialize conversation history if first message
    if "onboarding_history" not in context.user_data:
        context.user_data["onboarding_history"] = []

    history: list[dict] = context.user_data["onboarding_history"]

    # Append user message
    history.append({"role": "user", "content": text})

    try:
        # Build context summary for the prompt variable
        ctx["conversation_summary"] = _format_history_for_prompt(history[:-1])  # exclude latest user msg
        ctx["document_context"] = context.user_data.get("onboarding_document") or "No hay documento previo."

        system_prompt, _ = build_prompt("onboarding", ctx)

        # Generate response with full history
        reply = await generate_response(
            system_prompt=system_prompt,
            messages=history,
            max_tokens=400,
            temperature=0.6,
        )

        # Check for completion marker
        onboarding_done = _ONBOARDING_COMPLETE_MARKER in reply

        # Clean reply (remove the marker from what user sees)
        clean_reply = reply.replace(_ONBOARDING_COMPLETE_MARKER, "").strip()

        # Append assistant response to history
        history.append({"role": "assistant", "content": reply})

        await update.message.reply_text(clean_reply)

        if onboarding_done:
            await _finalize_onboarding(telegram_id, history, update, context)

    except FileNotFoundError as exc:
        logger.error("Prompt template missing: %s", exc)
        await update.message.reply_text(
            "Tuve un problema con la configuración del agente. Intenta de nuevo."
        )
    except Exception as exc:
        logger.error(
            "Error in onboarding handler for user %d: %s",
            telegram_id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("Tuve un problema técnico. Intenta de nuevo.")


def _format_history_for_prompt(history: list[dict]) -> str:
    """Format conversation history as readable text for the prompt template."""
    if not history:
        return "Primera interacción — no hay historial previo."
    lines = []
    for msg in history:
        role = "Usuario" if msg["role"] == "user" else "Vantara"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


async def _finalize_onboarding(
    telegram_id: int,
    history: list[dict],
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Extract project data from conversation and save to DB.
    Transition user to ACTIVE state.
    """
    from db.queries import create_project, update_conversation_state

    try:
        # Extract structured project data from the conversation
        extraction_prompt = """Extrae TODOS los proyectos capturados en esta conversación de onboarding — tanto los prioritarios como los "en el radar".
Responde SOLO con un JSON array con este formato exacto, sin texto adicional:
[
  {
    "name": "nombre del proyecto",
    "is_priority": true,
    "why_it_matters": "por qué importa",
    "objective": "objetivo final concreto",
    "next_milestone": "próximo hito a completar",
    "current_state": "estado actual y fases ya completadas",
    "next_action": "siguiente acción concreta esta semana",
    "acceptable_evidence": "qué cuenta como evidencia de avance"
  }
]
Proyectos prioritarios: is_priority=true. Proyectos "en el radar" o no prioritarios: is_priority=false.
Si algún campo no fue mencionado, usa null."""

        conversation_text = _format_history_for_prompt(history)
        extraction_user_msg = f"Conversación:\n{conversation_text}\n\nExtrae todos los proyectos en JSON."

        raw_json = await generate_response(
            system_prompt=extraction_prompt,
            user_message=extraction_user_msg,
            max_tokens=1200,
            temperature=0.1,
        )

        # Parse JSON (handle markdown code blocks if present)
        raw_json = raw_json.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        raw_json = raw_json.strip()

        projects = _json.loads(raw_json)

        # Save projects: priority ones first (lower priority number = higher priority)
        priority_counter = 1
        radar_counter = 100  # non-priority projects get high priority numbers
        for proj in projects:
            if not proj.get("name"):
                continue
            is_priority = proj.get("is_priority", True)
            p_number = priority_counter if is_priority else radar_counter
            if is_priority:
                priority_counter += 1
            else:
                radar_counter += 1
            create_project(
                user_id=telegram_id,
                name=proj["name"],
                priority=p_number,
                why_it_matters=proj.get("why_it_matters"),
                objective=proj.get("objective"),
                current_state=proj.get("current_state"),
                next_milestone=proj.get("next_milestone"),
                next_action=proj.get("next_action"),
                acceptable_evidence=proj.get("acceptable_evidence"),
            )

        # Transition to ACTIVE
        update_conversation_state(telegram_id, "ACTIVE")

        # Clear onboarding history from memory
        context.user_data.pop("onboarding_history", None)

        logger.info(
            "Onboarding complete for user %d — saved %d projects",
            telegram_id,
            len(projects),
        )

    except Exception as exc:
        logger.error(
            "Failed to finalize onboarding for user %d: %s",
            telegram_id,
            exc,
            exc_info=True,
        )
        # Still transition to ACTIVE even if project extraction failed
        from db.queries import update_conversation_state
        update_conversation_state(telegram_id, "ACTIVE")
        await update.message.reply_text(
            "Onboarding completado. No pude guardar todos los detalles de los proyectos automáticamente — usa /status para verificar."
        )


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


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Accepts a .txt file and uses it as context base for onboarding.
    Stores content in context.user_data["onboarding_document"].
    """
    if not check_user(update):
        return

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("Solo acepto archivos .txt por ahora.")
        return

    # 200KB limit — enough for any personal brief
    if doc.file_size and doc.file_size > 200 * 1024:
        await update.message.reply_text(
            "El archivo es muy grande. Máximo 200KB para archivos .txt."
        )
        return

    file_path = f"/tmp/doc_{doc.file_id}.txt"
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(file_path)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()

        if not content:
            await update.message.reply_text("El archivo está vacío.")
            return

        # Store for onboarding use
        context.user_data["onboarding_document"] = content

        await update.message.reply_text(
            "Leí tu documento. Voy a usarlo como base para el onboarding — "
            "te haré preguntas solo para completar o clarificar lo que necesite.\n\n"
            "Escríbeme cualquier cosa para comenzar."
        )

        # If already in onboarding, reset history so it starts fresh with the doc
        context.user_data.pop("onboarding_history", None)

    except Exception as exc:
        logger.error(
            "Error handling document for user %d: %s",
            update.effective_chat.id,
            exc,
            exc_info=True,
        )
        await update.message.reply_text("No pude leer el archivo. Intenta de nuevo.")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


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
