import asyncio
import logging

import groq

from config import settings

logger = logging.getLogger(__name__)

_FALLBACK_MESSAGE = "No pude generar una respuesta. Intenta de nuevo."
_MODEL = "llama-3.3-70b-versatile"

# Groq SDK client is sync — instantiated once at module level
_client = groq.Groq(api_key=settings.GROQ_API_KEY)


def _call_groq(system_prompt: str, user_message: str, max_tokens: int, temperature: float) -> str:
    """Synchronous Groq API call. Called via run_in_executor from async context."""
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content if response.choices else None
    return text or ""


def _call_groq_messages(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> str:
    """Sync Groq call with full conversation history."""
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content if response.choices else None
    return text or ""


async def generate_response(
    system_prompt: str,
    user_message: str | None = None,
    messages: list[dict] | None = None,
    max_tokens: int = 500,
    temperature: float = 0.7,
) -> str:
    """
    Wrapper del Groq SDK. Retorna solo el texto de la respuesta.

    Acepta user_message (single-turn) o messages (multi-turn con historial completo).
    Si se pasa messages, se usa _call_groq_messages; si no, _call_groq.

    Retry: 2 intentos en timeout/rate limit con backoff exponencial (1s, 2s).
    Respuesta vacía: retorna mensaje de fallback.
    Cualquier otro error: loggear + retornar mensaje de fallback.
    """
    loop = asyncio.get_running_loop()
    backoff_delays = [1, 2]

    use_messages = messages is not None

    for attempt, delay in enumerate(backoff_delays + [None], start=1):
        try:
            if use_messages:
                text = await loop.run_in_executor(
                    None,
                    _call_groq_messages,
                    system_prompt,
                    messages,
                    max_tokens,
                    temperature,
                )
            else:
                text = await loop.run_in_executor(
                    None, _call_groq, system_prompt, user_message or "", max_tokens, temperature
                )
            if not text or not text.strip():
                logger.warning("Groq returned an empty response on attempt %d", attempt)
                return _FALLBACK_MESSAGE
            return text

        except (groq.APIConnectionError, groq.APITimeoutError, groq.RateLimitError) as exc:
            if delay is not None:
                logger.warning(
                    "Groq transient error on attempt %d (%s), retrying in %ds",
                    attempt,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Groq transient error after %d attempts (%s), giving up",
                    attempt,
                    type(exc).__name__,
                )
                return _FALLBACK_MESSAGE

        except Exception as exc:
            logger.error("Unexpected Groq error: %s", exc, exc_info=True)
            return _FALLBACK_MESSAGE
