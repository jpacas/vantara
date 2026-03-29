"""
conftest.py — runs before all tests, installs module stubs so that
project imports never touch real databases, Telegram, or env vars.
Must be first to run (pytest collects conftest.py before test modules).
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# 1. config — prevent pydantic-settings from reading the environment
# ---------------------------------------------------------------------------
FAKE_SETTINGS = MagicMock()
FAKE_SETTINGS.TELEGRAM_TOKEN = "fake-token"
FAKE_SETTINGS.TELEGRAM_USER_ID = 12345
FAKE_SETTINGS.GROQ_API_KEY = "fake-groq"
FAKE_SETTINGS.OPENAI_API_KEY = "fake-openai"
FAKE_SETTINGS.DATABASE_URL = "postgresql://fake/db"

if "config" not in sys.modules:
    config_mod = types.ModuleType("config")
    config_mod.settings = FAKE_SETTINGS
    sys.modules["config"] = config_mod

# ---------------------------------------------------------------------------
# 2. db — prevent SQLAlchemy from creating an engine
# ---------------------------------------------------------------------------
if "db" not in sys.modules:
    sys.modules["db"] = types.ModuleType("db")

if "db.models" not in sys.modules:
    sys.modules["db.models"] = types.ModuleType("db.models")

# Populate db.queries with all functions that project code imports
_DB_QUERY_FUNCTIONS = [
    "get_user_state",
    "create_user_state",
    "update_conversation_state",
    "set_pause",
    "get_active_projects",
    "get_project_by_id",
    "create_project",
    "update_project",
    "get_todays_checkin",
    "create_checkin",
    "update_checkin",
    "get_open_commitments",
    "create_commitment",
    "fulfill_commitment",
    "break_commitment",
    "get_recent_evidence",
    "record_evidence",
    "get_days_since_movement",
    "get_open_blockers",
    "create_blocker",
    "resolve_blocker",
    "get_open_delegations",
    "create_delegation",
    "log_event",
]

if "db.queries" not in sys.modules:
    queries_mod = types.ModuleType("db.queries")
    for _fn in _DB_QUERY_FUNCTIONS:
        setattr(queries_mod, _fn, MagicMock())
    sys.modules["db.queries"] = queries_mod

# ---------------------------------------------------------------------------
# 3. telegram — prevent python-telegram-bot imports from resolving real classes
# ---------------------------------------------------------------------------
_telegram_classes = [
    "Update", "Message", "Chat", "User", "Document", "Voice",
    "File", "PhotoSize", "Audio",
]

if "telegram" not in sys.modules:
    telegram_mod = types.ModuleType("telegram")
    for _cls in _telegram_classes:
        setattr(telegram_mod, _cls, MagicMock)
    sys.modules["telegram"] = telegram_mod

_telegram_ext_classes = [
    "CallbackContext", "Application",
    "CommandHandler", "MessageHandler", "filters",
]

if "telegram.ext" not in sys.modules:
    telegram_ext_mod = types.ModuleType("telegram.ext")
    for _cls in _telegram_ext_classes:
        setattr(telegram_ext_mod, _cls, MagicMock)
    # ContextTypes.DEFAULT_TYPE must be a real attribute, not just MagicMock class
    _ContextTypes = MagicMock()
    _ContextTypes.DEFAULT_TYPE = MagicMock()
    telegram_ext_mod.ContextTypes = _ContextTypes
    sys.modules["telegram.ext"] = telegram_ext_mod

# Other telegram sub-modules that might be imported transitively
for _sub in ["telegram.error", "telegram.constants"]:
    if _sub not in sys.modules:
        sys.modules[_sub] = types.ModuleType(_sub)

# ---------------------------------------------------------------------------
# 4. groq + openai — prevent real SDK imports
# ---------------------------------------------------------------------------
if "groq" not in sys.modules:
    groq_mod = types.ModuleType("groq")
    groq_mod.Groq = MagicMock
    groq_mod.APIConnectionError = Exception
    groq_mod.APITimeoutError = Exception
    groq_mod.RateLimitError = Exception
    sys.modules["groq"] = groq_mod

if "openai" not in sys.modules:
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = MagicMock
    openai_mod.APIError = Exception
    sys.modules["openai"] = openai_mod

# ---------------------------------------------------------------------------
# 5. agent.groq_client — stub generate_response so groq_client.py's
#    module-level `_client = groq.Groq(...)` never runs with a real key
# ---------------------------------------------------------------------------
# Note: do NOT pre-stub "agent" as a plain ModuleType — the real agent/ package
# exists on disk and Python must find it as a real package so that
# `from agent.context_builder import build_context` resolves correctly.
# Only stub sub-modules that would trigger unwanted side effects at import time.

if "agent.groq_client" not in sys.modules:
    groq_client_mod = types.ModuleType("agent.groq_client")
    groq_client_mod.generate_response = AsyncMock(return_value="mocked response")
    sys.modules["agent.groq_client"] = groq_client_mod

# ---------------------------------------------------------------------------
# 6. agent.prompt_builder — stub build_prompt so no file I/O needed
# ---------------------------------------------------------------------------
if "agent.prompt_builder" not in sys.modules:
    prompt_builder_mod = types.ModuleType("agent.prompt_builder")
    prompt_builder_mod.build_prompt = MagicMock(return_value=("system", "user"))
    sys.modules["agent.prompt_builder"] = prompt_builder_mod
