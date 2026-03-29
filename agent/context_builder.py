import asyncio
import logging
from datetime import datetime, timezone

from db.queries import (
    get_active_projects,
    get_days_since_movement,
    get_open_blockers,
    get_open_commitments,
    get_open_delegations,
    get_recent_evidence,
    get_user_state,
)

logger = logging.getLogger(__name__)


async def build_context(telegram_id: int) -> dict:
    """
    ÚNICA función que lee el estado del usuario desde DB para el LLM.
    Llamada por todos los jobs y handlers — NO duplicar esta lógica.

    Retorna dict con:
      - user_state: dict con conversation_state, is_paused (bool), pause_until (str o None)
      - projects: lista de dicts, cada uno con todos los campos del proyecto + days_since_movement
      - todays_commitments: lista de compromisos abiertos del día de hoy
      - recent_evidence: lista de evidencias de los últimos 7 días
      - open_blockers: lista de bloqueadores activos
      - open_delegations: lista de delegaciones pendientes

    Si la DB falla, la excepción se propaga — el caller es quien notifica al usuario.
    Si no existe user_state para el telegram_id, retorna contexto vacío (no crashea).
    """
    loop = asyncio.get_event_loop()

    # All DB calls are sync — run in executor to avoid blocking the event loop
    user_row = await loop.run_in_executor(None, get_user_state, telegram_id)

    if user_row is None:
        # New user — return empty context, do not crash
        return {
            "user_state": {
                "conversation_state": "ONBOARDING_PENDING",
                "is_paused": False,
                "pause_until": None,
            },
            "projects": [],
            "todays_commitments": [],
            "recent_evidence": [],
            "open_blockers": [],
            "open_delegations": [],
        }

    # Calculate is_paused deterministically
    pause_until = user_row.pause_until
    if pause_until is not None and pause_until.tzinfo is None:
        # Treat naive datetimes stored in DB as UTC
        pause_until = pause_until.replace(tzinfo=timezone.utc)

    is_paused = pause_until is not None and pause_until > datetime.now(tz=timezone.utc)

    user_state_dict = {
        "conversation_state": user_row.conversation_state,
        "is_paused": is_paused,
        "pause_until": pause_until.isoformat() if pause_until is not None else None,
    }

    # Fetch projects and enrich with days_since_movement
    project_rows = await loop.run_in_executor(None, get_active_projects, telegram_id)

    projects = []
    for p in project_rows:
        days = await loop.run_in_executor(None, get_days_since_movement, p.id)
        projects.append({
            "id": p.id,
            "name": p.name,
            "priority": p.priority,
            "why_it_matters": p.why_it_matters,
            "objective": p.objective,
            "current_state": p.current_state,
            "next_milestone": p.next_milestone,
            "next_action": p.next_action,
            "acceptable_evidence": p.acceptable_evidence,
            "progress_pct": p.progress_pct,
            "is_active": p.is_active,
            "days_since_movement": days,
        })

    # Fetch commitments, evidence, blockers, delegations
    commitment_rows = await loop.run_in_executor(None, get_open_commitments, telegram_id)
    todays_commitments = [
        {
            "id": c.id,
            "project_id": c.project_id,
            "description": c.description,
            "due_date": c.due_date.isoformat() if c.due_date is not None else None,
            "status": c.status,
        }
        for c in commitment_rows
    ]

    evidence_rows = await loop.run_in_executor(None, get_recent_evidence, telegram_id)
    recent_evidence = [
        {
            "id": e.id,
            "project_id": e.project_id,
            "description": e.description,
            "evidence_type": e.evidence_type,
            "recorded_at": e.recorded_at.isoformat(),
        }
        for e in evidence_rows
    ]

    blocker_rows = await loop.run_in_executor(None, get_open_blockers, telegram_id)
    open_blockers = [
        {
            "id": b.id,
            "project_id": b.project_id,
            "description": b.description,
        }
        for b in blocker_rows
    ]

    delegation_rows = await loop.run_in_executor(None, get_open_delegations, telegram_id)
    open_delegations = [
        {
            "id": d.id,
            "project_id": d.project_id,
            "description": d.description,
            "delegated_to": d.delegated_to,
            "follow_up_date": d.follow_up_date.isoformat() if d.follow_up_date is not None else None,
            "status": d.status,
        }
        for d in delegation_rows
    ]

    return {
        "user_state": user_state_dict,
        "projects": projects,
        "todays_commitments": todays_commitments,
        "recent_evidence": recent_evidence,
        "open_blockers": open_blockers,
        "open_delegations": open_delegations,
    }
