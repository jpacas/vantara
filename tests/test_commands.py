"""
Tests for bot/commands.py — command handlers.
All DB and Telegram dependencies are mocked via tests/conftest.py.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands import pause_command, status_command

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AUTHORIZED_ID = 12345
UNAUTHORIZED_ID = 99999


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(chat_id: int):
    """Build a minimal mock Update."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    return update


def _make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


# ---------------------------------------------------------------------------
# pause_command tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_3_days_sets_correct_pause_until():
    """/pause 3 → set_pause llamado con datetime ~3 días desde ahora."""
    update = _make_update(AUTHORIZED_ID)
    context = _make_context(args=["3"])

    with patch("bot.commands.set_pause") as mock_set_pause:
        await pause_command(update, context)

    mock_set_pause.assert_called_once()
    _, pause_until = mock_set_pause.call_args[0]

    now = datetime.now(tz=timezone.utc)
    expected_min = now + timedelta(days=2, hours=23)
    expected_max = now + timedelta(days=3, hours=1)

    assert expected_min <= pause_until <= expected_max, (
        f"pause_until {pause_until} not within 3-day window"
    )


@pytest.mark.asyncio
async def test_pause_0_clears_pause():
    """/pause 0 → set_pause llamado con None (cancela la pausa)."""
    update = _make_update(AUTHORIZED_ID)
    context = _make_context(args=["0"])

    with patch("bot.commands.set_pause") as mock_set_pause:
        await pause_command(update, context)

    mock_set_pause.assert_called_once_with(AUTHORIZED_ID, None)


@pytest.mark.asyncio
async def test_status_no_projects_replies_onboarding():
    """/status sin proyectos → mensaje menciona 'onboarding' o 'no tienes proyectos'."""
    update = _make_update(AUTHORIZED_ID)
    context = _make_context()

    empty_ctx = {
        "projects": [],
        "user_state": {"conversation_state": "ACTIVE", "is_paused": False, "pause_until": None},
        "open_commitments": [],
        "recent_evidence": [],
        "open_blockers": [],
        "open_delegations": [],
    }

    with patch("bot.commands.build_context", new=AsyncMock(return_value=empty_ctx)):
        await status_command(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0].lower()
    assert "onboarding" in reply_text or "no tienes proyectos" in reply_text, (
        f"Expected onboarding message, got: {reply_text!r}"
    )


@pytest.mark.asyncio
async def test_unknown_chat_id_ignored():
    """Chat ID no autorizado → ningún reply enviado."""
    update = _make_update(UNAUTHORIZED_ID)
    context = _make_context(args=["1"])

    with patch("bot.commands.set_pause") as mock_set_pause:
        await pause_command(update, context)

    update.message.reply_text.assert_not_called()
    mock_set_pause.assert_not_called()
