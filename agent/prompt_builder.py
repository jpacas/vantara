import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def build_prompt(mode: str, context: dict) -> tuple[str, str]:
    """
    Carga template de /prompts/{mode}.txt.
    Inyecta context en el template usando str.format_map(context).
    Retorna (system_prompt, user_message).

    system_prompt: contenido de prompts/system.txt (siempre inyectado)
    user_message:  contenido de prompts/{mode}.txt con context inyectado

    Lanza FileNotFoundError si el template no existe — NO swallow.
    Lanza KeyError si el template usa una variable que no está en context — NO swallow.
    """
    system_path = PROMPTS_DIR / "system.txt"
    if not system_path.exists():
        raise FileNotFoundError(
            f"System prompt not found: {system_path}. "
            "Ensure prompts/system.txt exists."
        )

    mode_path = PROMPTS_DIR / f"{mode}.txt"
    if not mode_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found for mode '{mode}': {mode_path}."
        )

    system_prompt = system_path.read_text(encoding="utf-8")
    mode_template = mode_path.read_text(encoding="utf-8")

    # format_map raises KeyError if a placeholder in the template is missing from context
    user_message = mode_template.format_map(context)

    return system_prompt, user_message
