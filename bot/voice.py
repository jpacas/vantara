import logging
import os

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

whisper = OpenAI(api_key=settings.OPENAI_API_KEY)


async def transcribe_voice(file_path: str) -> str | None:
    """
    Transcribe an audio file using OpenAI Whisper.
    Returns transcribed text or None if it fails.
    Validates file size before calling (returns None if > 25MB).
    """
    # Validate file size
    file_size = os.path.getsize(file_path)
    if file_size > _MAX_FILE_SIZE:
        logger.warning(f"Voice file too large: {file_size} bytes")
        return None

    try:
        with open(file_path, "rb") as audio_file:
            response = whisper.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = response.text.strip()
        if not text:
            logger.warning("Whisper returned empty transcription")
            return None
        return text
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        return None
