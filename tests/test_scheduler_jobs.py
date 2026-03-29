"""
Tests for scheduler/jobs.py — scheduled job handlers.
All DB and Telegram dependencies are mocked via tests/conftest.py.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scheduler.jobs import morning_checkin_job, stagnation_check_job

# ---------------------------------------------------------------------------
# Constants / patch targets
# ---------------------------------------------------------------------------
USER_ID = 12345

PATCH_GET_USER = "scheduler.jobs.get_user_state"
PATCH_CREATE_CHECKIN = "scheduler.jobs.create_checkin"
PATCH_BUILD_CONTEXT = "scheduler.jobs.build_context"
PATCH_BUILD_PROMPT = "scheduler.jobs.build_prompt"
PATCH_GENERATE = "scheduler.jobs.generate_response"
PATCH_UPDATE_CHECKIN = "scheduler.jobs.update_checkin"
PATCH_LOG_EVENT = "scheduler.jobs.log_event"
PATCH_GET_PROJECTS = "scheduler.jobs.get_active_projects"
PATCH_GET_DAYS = "scheduler.jobs.get_days_since_movement"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(conversation_state="ACTIVE", pause_until=None):
    user = MagicMock()
    user.conversation_state = conversation_state
    user.pause_until = pause_until
    return user


def _make_project(project_id=1, name="Proyecto A"):
    p = MagicMock()
    p.id = project_id
    p.name = name
    p.priority = 1
    return p


def _make_checkin(checkin_id=1):
    c = MagicMock()
    c.id = checkin_id
    return c


def _make_job_context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _valid_context_dict():
    return {
        "user_state": {"conversation_state": "ACTIVE", "is_paused": False, "pause_until": None},
        "projects": [],
        "open_commitments": [],
        "recent_evidence": [],
        "open_blockers": [],
        "open_delegations": [],
    }


# ---------------------------------------------------------------------------
# morning_checkin_job tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_morning_checkin_skips_when_paused():
    """morning_checkin_job con usuario en pausa → no envía mensaje."""
    paused_user = _make_user(
        conversation_state="ACTIVE",
        pause_until=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    job_ctx = _make_job_context()

    with patch(PATCH_GET_USER, return_value=paused_user):
        await morning_checkin_job(job_ctx)

    job_ctx.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_morning_checkin_skips_when_checkin_already_exists():
    """morning_checkin_job con checkin ya existente → no envía duplicado."""
    active_user = _make_user(conversation_state="ACTIVE", pause_until=None)
    job_ctx = _make_job_context()

    with (
        patch(PATCH_GET_USER, return_value=active_user),
        patch(PATCH_CREATE_CHECKIN, return_value=None),  # None = ya existe
    ):
        await morning_checkin_job(job_ctx)

    job_ctx.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_morning_checkin_skips_when_onboarding():
    """morning_checkin_job con usuario en ONBOARDING → no envía mensaje."""
    onboarding_user = _make_user(conversation_state="ONBOARDING_IN_PROGRESS", pause_until=None)
    job_ctx = _make_job_context()

    with patch(PATCH_GET_USER, return_value=onboarding_user):
        await morning_checkin_job(job_ctx)

    job_ctx.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_morning_checkin_sends_when_active():
    """morning_checkin_job usuario activo sin checkin previo → envía mensaje."""
    active_user = _make_user(conversation_state="ACTIVE", pause_until=None)
    checkin = _make_checkin()
    job_ctx = _make_job_context()

    with (
        patch(PATCH_GET_USER, return_value=active_user),
        patch(PATCH_CREATE_CHECKIN, return_value=checkin),
        patch(PATCH_BUILD_CONTEXT, new=AsyncMock(return_value=_valid_context_dict())),
        patch(PATCH_BUILD_PROMPT, return_value=("system", "user")),
        patch(PATCH_GENERATE, new=AsyncMock(return_value="Buenos días!")),
        patch(PATCH_UPDATE_CHECKIN),
        patch(PATCH_LOG_EVENT),
    ):
        await morning_checkin_job(job_ctx)

    job_ctx.bot.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# stagnation_check_job tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stagnation_check_skips_when_paused():
    """stagnation_check_job con usuario en pausa → no confronta."""
    paused_user = _make_user(
        conversation_state="ACTIVE",
        pause_until=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    job_ctx = _make_job_context()

    with patch(PATCH_GET_USER, return_value=paused_user):
        await stagnation_check_job(job_ctx)

    job_ctx.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_stagnation_check_confronts_when_project_stagnant():
    """stagnation_check_job con proyecto > 5 días → genera confrontación y envía mensaje."""
    active_user = _make_user(conversation_state="ACTIVE", pause_until=None)
    project = _make_project()
    job_ctx = _make_job_context()

    ctx_dict = _valid_context_dict()
    ctx_dict["projects"] = [
        {"id": 1, "name": "Proyecto A", "days_since_movement": 6, "priority": 1}
    ]

    with (
        patch(PATCH_GET_USER, return_value=active_user),
        patch(PATCH_GET_PROJECTS, return_value=[project]),
        patch(PATCH_GET_DAYS, return_value=6),
        patch(PATCH_BUILD_CONTEXT, new=AsyncMock(return_value=ctx_dict)),
        patch(PATCH_BUILD_PROMPT, return_value=("system", "user")),
        patch(PATCH_GENERATE, new=AsyncMock(return_value="Confrontación directa.")),
        patch(PATCH_LOG_EVENT),
    ):
        await stagnation_check_job(job_ctx)

    job_ctx.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_stagnation_check_no_message_when_project_not_stagnant():
    """stagnation_check_job con proyecto ≤ 5 días → no confronta."""
    active_user = _make_user(conversation_state="ACTIVE", pause_until=None)
    project = _make_project()
    job_ctx = _make_job_context()

    ctx_dict = _valid_context_dict()

    with (
        patch(PATCH_GET_USER, return_value=active_user),
        patch(PATCH_GET_PROJECTS, return_value=[project]),
        patch(PATCH_GET_DAYS, return_value=3),  # ≤ 5 → no confrontation
        patch(PATCH_BUILD_CONTEXT, new=AsyncMock(return_value=ctx_dict)),
        patch(PATCH_LOG_EVENT),
    ):
        await stagnation_check_job(job_ctx)

    job_ctx.bot.send_message.assert_not_called()
