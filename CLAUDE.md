# Vantara — Sistema de ejecución personal por Telegram

Bot de Telegram que actúa como agente de accountability: prioriza, confronta, hace seguimiento y exige evidencia para asegurar avances reales en proyectos prioritarios.

## Tech Stack

- **Python 3.12**
- **python-telegram-bot v20** con `[job-queue]` (scheduler integrado via PTB JobQueue, no APScheduler standalone)
- **Groq API** (LLM — modelo `llama-3.3-70b-versatile`) via SDK `groq`
- **OpenAI Whisper API** (transcripción de notas de voz únicamente)
- **Supabase** (PostgreSQL) via `supabase-py` + `SQLAlchemy`
- **pydantic-settings** (configuración desde env vars)
- **Railway** hobby plan (no usar el plan gratuito — el proceso debe estar corriendo siempre para el JobQueue)

## Estructura del proyecto

```
vantara/
├── main.py                    # entrypoint: Application + JobQueue setup
├── config.py                  # Settings via pydantic-settings
├── requirements.txt
├── .env.example
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py            # handle_text_message(), handle_voice_message()
│   ├── commands.py            # /start /status /unblock /delegate /pause
│   └── voice.py              # Whisper transcription
│
├── agent/
│   ├── __init__.py
│   ├── context_builder.py     # DB → context dict (única fuente de contexto)
│   ├── prompt_builder.py      # context dict + template file → prompt string
│   └── groq_client.py         # Groq SDK wrapper
│
├── scheduler/
│   ├── __init__.py
│   └── jobs.py               # PTB JobQueue job definitions
│
├── db/
│   ├── __init__.py
│   ├── models.py             # SQLAlchemy models
│   └── queries.py            # todas las queries en un solo lugar
│
├── prompts/                  # templates como archivos .txt, NO strings en código
│   ├── system.txt            # system prompt base (siempre inyectado)
│   ├── morning.txt
│   ├── midday.txt
│   ├── evening.txt
│   ├── weekly.txt
│   ├── onboarding.txt
│   ├── confrontation.txt
│   └── unblock.txt
│
└── tests/
    ├── test_context_builder.py
    ├── test_commands.py
    ├── test_scheduler_jobs.py
    └── evals/
        └── confrontation_cases.json  # casos para validar calidad de confrontación
```

## Variables de entorno requeridas

```env
TELEGRAM_TOKEN=...
TELEGRAM_USER_ID=...          # tu Telegram user ID — bot solo responde a este ID
GROQ_API_KEY=...
OPENAI_API_KEY=...            # solo para Whisper transcription
DATABASE_URL=...              # Supabase connection string (postgres://...)
```

## Base de datos — Schema

```sql
-- Estado de conversación del usuario
CREATE TABLE user_state (
  id            SERIAL PRIMARY KEY,
  telegram_id   BIGINT UNIQUE NOT NULL,
  conversation_state TEXT DEFAULT 'ONBOARDING_PENDING',
  -- Estados: ONBOARDING_PENDING | ONBOARDING_IN_PROGRESS | ACTIVE | PAUSED
  pause_until   TIMESTAMP,
  checkin_times JSONB DEFAULT '{"morning":"08:00","midday":"13:00","evening":"19:00"}',
  created_at    TIMESTAMP DEFAULT NOW(),
  updated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE projects (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  name          TEXT NOT NULL,
  priority      INTEGER NOT NULL,  -- 1=highest
  why_it_matters TEXT,
  objective     TEXT,
  current_state TEXT,
  next_milestone TEXT,
  next_action   TEXT,
  acceptable_evidence TEXT,
  progress_pct  INTEGER DEFAULT 0,  -- calculado deterministamente, nunca por LLM
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMP DEFAULT NOW(),
  updated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE checkins (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  checkin_type  TEXT NOT NULL,  -- morning | midday | evening | weekly
  date          DATE NOT NULL DEFAULT CURRENT_DATE,
  bot_message   TEXT,
  user_response TEXT,
  status        TEXT DEFAULT 'pending',  -- pending | responded | skipped
  created_at    TIMESTAMP DEFAULT NOW(),
  UNIQUE (user_id, date, checkin_type)   -- previene duplicados por restart
);

CREATE TABLE commitments (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  project_id    INTEGER REFERENCES projects(id),
  checkin_id    INTEGER REFERENCES checkins(id),
  description   TEXT NOT NULL,
  due_date      DATE,
  status        TEXT DEFAULT 'open',  -- open | fulfilled | broken
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE evidence (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  project_id    INTEGER REFERENCES projects(id),
  commitment_id INTEGER REFERENCES commitments(id),
  description   TEXT NOT NULL,
  evidence_type TEXT,  -- text | voice | file
  recorded_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE blockers (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  project_id    INTEGER REFERENCES projects(id),
  description   TEXT NOT NULL,
  is_resolved   BOOLEAN DEFAULT FALSE,
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE delegations (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES user_state(telegram_id),
  project_id    INTEGER REFERENCES projects(id),
  description   TEXT NOT NULL,
  delegated_to  TEXT,
  follow_up_date DATE,
  status        TEXT DEFAULT 'pending',  -- pending | done | overdue
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE system_logs (
  id            SERIAL PRIMARY KEY,
  user_id       BIGINT,
  event_type    TEXT,  -- checkin_sent | evidence_recorded | job_error | etc.
  payload       JSONB,
  created_at    TIMESTAMP DEFAULT NOW()
);
```

## Decisiones de diseño — NO cambiar sin razón explícita

1. **Scheduler:** PTB JobQueue built-in (`python-telegram-bot[job-queue]`). No usar APScheduler standalone — corre en el mismo asyncio event loop de PTB, sin conflictos.

2. **Progreso de proyectos:** DETERMINISTA. La columna `progress_pct` se calcula con una función Python basada en evidencias registradas y compromisos cumplidos. El LLM nunca genera ni estima porcentajes — solo los interpreta al presentarlos.

3. **Estado de conversación:** En DB (`user_state.conversation_state`). No en memoria (se pierde en restart de Railway). No en PicklePersistence (menos transparente). DB es la fuente de verdad.

4. **Prompts:** Archivos `.txt` en `/prompts/`. NUNCA como f-strings en código Python. Esto permite iterar el tono y la personalidad del agente sin tocar lógica.

5. **Context builder:** `build_context()` en `agent/context_builder.py` es la ÚNICA función que lee el estado del usuario desde DB para armar el contexto del LLM. Todos los jobs y handlers la llaman — no duplicar esta lógica.

6. **Error handling en context_builder:** Si la DB no está disponible, notificar al usuario por Telegram con un mensaje simple. No crashear silenciosamente.

7. **Voice:** OpenAI Whisper API para transcripción. Validar tamaño del archivo antes de llamar a Whisper (límite: 25MB). Si falla, pedirle al usuario que escriba el mensaje.

8. **Single user:** El bot solo responde a `TELEGRAM_USER_ID`. Ignorar cualquier otro chat_id desde el inicio del handler.

## Groq — Modelo y configuración

```python
from groq import Groq

client = Groq(api_key=settings.GROQ_API_KEY)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    max_tokens=500,    # mensajes cortos — el agente debe ser breve
    temperature=0.7
)
```

Modelos disponibles en Groq (en orden de capacidad):
- `llama-3.3-70b-versatile` — usar este para confrontación y análisis
- `llama-3.1-8b-instant` — si necesitas respuestas más rápidas en comandos simples

## Testing

```bash
# Instalar dependencias
pip install -r requirements.txt

# Correr tests
pytest tests/ -v

# Correr evals de confrontación (después de tener prompts escritos)
python tests/evals/run_confrontation_evals.py
```

## Comandos del bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Inicia onboarding si es primera vez |
| `/status` | Tabla de estado de todos los proyectos activos |
| `/unblock [proyecto]` | Dispara motor de desbloqueo para un proyecto |
| `/delegate` | Inicia flujo de delegación estructurada |
| `/pause [días]` | Pausa el scheduler N días (default: 1). `/pause 0` cancela la pausa |

## Flujo de conversación — Estados

```
ONBOARDING_PENDING
      │
      ▼ /start
ONBOARDING_IN_PROGRESS
      │
      ▼ onboarding completado
   ACTIVE ◄──────────────────────────────┐
      │                                  │
      ├── [scheduler dispara]            │
      │   morning / midday / evening     │
      │   weekly (viernes)               │
      │   stagnation_check (nightly)     │
      │                                  │
      ├── [usuario escribe] → free form  │
      │                                  │
      └── /pause → PAUSED ──────────────►┘
                   (pause_until en DB)
```

## Deploy en Railway

1. Crear proyecto en Railway
2. Agregar variables de entorno (ver sección arriba)
3. Usar **Hobby plan** ($5/mo) — el plan gratuito duerme y rompe el scheduler
4. Asegurarse de que el proceso corre `python main.py` (no `uvicorn` — no hay HTTP server)
5. Railway detecta Python automáticamente por `requirements.txt`

## Notas de seguridad

- El bot verifica `chat_id == TELEGRAM_USER_ID` en cada handler antes de procesar
- API keys solo en variables de entorno, nunca en código
- No hay endpoint HTTP expuesto — el bot corre en modo polling
