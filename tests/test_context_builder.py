"""
Tests for agent/context_builder.py — build_context()
All DB dependencies are mocked; no live database required.
Stubs are installed via tests/conftest.py before any import.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from agent.context_builder import build_context

# ---------------------------------------------------------------------------
# Patch targets (functions re-exported into agent.context_builder's namespace)
# ---------------------------------------------------------------------------
PATCH_GET_USER = "agent.context_builder.get_user_state"
PATCH_GET_PROJECTS = "agent.context_builder.get_active_projects"
PATCH_GET_DAYS = "agent.context_builder.get_days_since_movement"
PATCH_GET_COMMITMENTS = "agent.context_builder.get_open_commitments"
PATCH_GET_EVIDENCE = "agent.context_builder.get_recent_evidence"
PATCH_GET_BLOCKERS = "agent.context_builder.get_open_blockers"
PATCH_GET_DELEGATIONS = "agent.context_builder.get_open_delegations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(conversation_state="ACTIVE", pause_until=None):
    from unittest.mock import MagicMock
    user = MagicMock()
    user.conversation_state = conversation_state
    user.pause_until = pause_until
    return user


def _make_project(project_id=1, name="Proyecto A", priority=1):
    from unittest.mock import MagicMock
    p = MagicMock()
    p.id = project_id
    p.name = name
    p.priority = priority
    p.why_it_matters = None
    p.objective = None
    p.current_state = None
    p.next_milestone = None
    p.next_action = None
    p.acceptable_evidence = None
    p.progress_pct = 0
    p.is_active = True
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_projects_returns_empty_list():
    """Usuario sin proyectos → projects list vacía, conversation_state correcto."""
    user = _make_user(conversation_state="ACTIVE", pause_until=None)

    with (
        patch(PATCH_GET_USER, return_value=user),
        patch(PATCH_GET_PROJECTS, return_value=[]),
        patch(PATCH_GET_COMMITMENTS, return_value=[]),
        patch(PATCH_GET_EVIDENCE, return_value=[]),
        patch(PATCH_GET_BLOCKERS, return_value=[]),
        patch(PATCH_GET_DELEGATIONS, return_value=[]),
    ):
        context = await build_context(12345)

    assert context["projects"] == []
    assert context["user_state"]["conversation_state"] == "ACTIVE"


@pytest.mark.asyncio
async def test_project_days_since_movement():
    """Proyecto con evidencia reciente → days_since_movement correcto en context."""
    user = _make_user(conversation_state="ACTIVE", pause_until=None)
    project = _make_project()

    with (
        patch(PATCH_GET_USER, return_value=user),
        patch(PATCH_GET_PROJECTS, return_value=[project]),
        patch(PATCH_GET_DAYS, return_value=3),
        patch(PATCH_GET_COMMITMENTS, return_value=[]),
        patch(PATCH_GET_EVIDENCE, return_value=[]),
        patch(PATCH_GET_BLOCKERS, return_value=[]),
        patch(PATCH_GET_DELEGATIONS, return_value=[]),
    ):
        context = await build_context(12345)

    assert len(context["projects"]) == 1
    assert context["projects"][0]["days_since_movement"] == 3


@pytest.mark.asyncio
async def test_user_not_found_returns_onboarding_pending():
    """Usuario no existe → contexto vacío con ONBOARDING_PENDING."""
    with patch(PATCH_GET_USER, return_value=None):
        context = await build_context(99999)

    assert context["user_state"]["conversation_state"] == "ONBOARDING_PENDING"
    assert context["projects"] == []
    assert context["open_commitments"] == []
    assert context["recent_evidence"] == []
    assert context["open_blockers"] == []
    assert context["open_delegations"] == []


@pytest.mark.asyncio
async def test_is_paused_true_when_pause_until_in_future():
    """is_paused=True cuando pause_until está en el futuro."""
    future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    user = _make_user(conversation_state="ACTIVE", pause_until=future)

    with (
        patch(PATCH_GET_USER, return_value=user),
        patch(PATCH_GET_PROJECTS, return_value=[]),
        patch(PATCH_GET_COMMITMENTS, return_value=[]),
        patch(PATCH_GET_EVIDENCE, return_value=[]),
        patch(PATCH_GET_BLOCKERS, return_value=[]),
        patch(PATCH_GET_DELEGATIONS, return_value=[]),
    ):
        context = await build_context(12345)

    assert context["user_state"]["is_paused"] is True
    assert context["user_state"]["pause_until"] is not None


@pytest.mark.asyncio
async def test_is_paused_false_when_pause_until_in_past():
    """is_paused=False cuando pause_until ya expiró; pause_until en contexto es None."""
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    user = _make_user(conversation_state="ACTIVE", pause_until=past)

    with (
        patch(PATCH_GET_USER, return_value=user),
        patch(PATCH_GET_PROJECTS, return_value=[]),
        patch(PATCH_GET_COMMITMENTS, return_value=[]),
        patch(PATCH_GET_EVIDENCE, return_value=[]),
        patch(PATCH_GET_BLOCKERS, return_value=[]),
        patch(PATCH_GET_DELEGATIONS, return_value=[]),
    ):
        context = await build_context(12345)

    assert context["user_state"]["is_paused"] is False
    assert context["user_state"]["pause_until"] is None
