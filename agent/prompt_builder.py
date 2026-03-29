import logging
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _format_projects(projects: list[dict]) -> str:
    """Format projects list into a human-readable string for template injection."""
    if not projects:
        return "Ninguno"
    lines = []
    for p in projects:
        days = p.get("days_since_movement")
        days_str = f"{days} días sin movimiento" if days is not None else "sin datos de movimiento"
        lines.append(f"[P{p['priority']}] {p['name']} — {days_str}")
        if p.get("objective"):
            lines.append(f"     Objetivo: {p['objective']}")
        if p.get("next_action"):
            lines.append(f"     Próxima acción: {p['next_action']}")
    return "\n".join(lines)


def _format_list(items: list[dict], key: str) -> str:
    """Format a list of dicts into a numbered string using a given key, or 'Ninguno'."""
    if not items:
        return "Ninguno"
    return "\n".join(f"{i + 1}. {item.get(key, '')}" for i, item in enumerate(items))


def _flatten_context(context: dict) -> dict[str, str]:
    """
    Flatten the nested context dict from build_context() into a flat dict of strings
    suitable for string.Template substitution in prompt templates.
    """
    user_state = context.get("user_state", {})
    return {
        "conversation_state": str(user_state.get("conversation_state", "ONBOARDING_PENDING")),
        "is_paused": str(user_state.get("is_paused", False)),
        "pause_until": str(user_state.get("pause_until") or "N/A"),
        "projects_summary": _format_projects(context.get("projects", [])),
        "commitments_summary": _format_list(context.get("open_commitments", []), "description"),
        "evidence_summary": _format_list(context.get("recent_evidence", []), "description"),
        "blockers_summary": _format_list(context.get("open_blockers", []), "description"),
        "delegations_summary": _format_list(context.get("open_delegations", []), "description"),
    }


def build_prompt(mode: str, context: dict) -> tuple[str, str]:
    """
    Carga template de /prompts/{mode}.txt.
    Inyecta context en el template usando string.Template con sintaxis $variable.
    Retorna (system_prompt, user_message).

    system_prompt: contenido de prompts/system.txt (siempre inyectado)
    user_message:  contenido de prompts/{mode}.txt con context inyectado

    Los templates deben usar $variable (string.Template), NO {variable} (str.format_map).
    safe_substitute se usa para que variables no encontradas se dejen sin reemplazar
    en lugar de lanzar KeyError.

    Lanza FileNotFoundError si el template no existe — NO swallow.
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

    system_txt = system_path.read_text(encoding="utf-8")
    mode_txt = mode_path.read_text(encoding="utf-8")

    flat = _flatten_context(context)

    system_prompt = Template(system_txt).safe_substitute(flat)
    user_message = Template(mode_txt).safe_substitute(flat)

    return system_prompt, user_message
