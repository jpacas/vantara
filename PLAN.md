# Plan de implementación — Vantara MVP

Fecha: 2026-03-28
Revisado por: CEO Review + Eng Review (ver abajo)

## Contexto rápido

Bot de Telegram que actúa como agente de accountability personal. Prioriza, confronta, hace seguimiento y exige evidencia de avance en proyectos prioritarios.

Lee `CLAUDE.md` antes de empezar — contiene el tech stack completo, el schema de DB, y las decisiones de diseño que NO se deben cambiar sin razón explícita.

Lee `Vantara.md` para entender el producto, la personalidad del agente, y los casos de uso.

---

## ANTES de implementar (P0)

**Escribir el guión de conversación.** Antes de tocar código, el usuario debe escribir a mano 10-15 mensajes de ejemplo de cómo debe sonar el bot en la primera semana:
- Cómo empieza el onboarding (qué pregunta primero, en qué tono)
- Cómo suena el check-in mañanero
- Cómo suena la confrontación de un proyecto estancado (ejemplo concreto)
- Cuántas líneas máximo por mensaje

Esto define los archivos en `/prompts/`. Sin esto, el bot va a sonar genérico.

---

## Fase 1A — DB Schema (independiente, empezar aquí)

**Objetivo:** Supabase corriendo con el schema completo.

### Pasos

1. Crear proyecto en Supabase
2. Ejecutar el SQL del schema completo (ver `CLAUDE.md` sección "Base de datos")
3. Copiar la connection string a `.env` como `DATABASE_URL`
4. Verificar: conectar desde Python con `psycopg2` y hacer un `SELECT 1`

### Entregables
- [ ] Supabase project creado
- [ ] Todas las tablas creadas con constraints
- [ ] Unique constraint en `checkins(user_id, date, checkin_type)` confirmado
- [ ] Conexión Python verificada

---

## Fase 1B — Bot skeleton + comandos (independiente, paralelo con 1A)

**Objetivo:** Bot de Telegram corriendo en Railway que responde a comandos básicos.

### Pasos

1. Instalar dependencias base:
   ```
   python-telegram-bot[job-queue]==20.*
   pydantic-settings
   python-dotenv
   ```

2. Crear `config.py` con `pydantic-settings`:
   ```python
   from pydantic_settings import BaseSettings

   class Settings(BaseSettings):
       TELEGRAM_TOKEN: str
       TELEGRAM_USER_ID: int
       GROQ_API_KEY: str
       OPENAI_API_KEY: str
       DATABASE_URL: str

       class Config:
           env_file = ".env"

   settings = Settings()
   ```

3. Crear `main.py` — Application setup con PTB:
   ```python
   from telegram.ext import Application, CommandHandler, MessageHandler, filters

   async def main():
       app = Application.builder().token(settings.TELEGRAM_TOKEN).build()
       # registrar handlers
       # registrar jobs en app.job_queue
       await app.run_polling()
   ```

4. Crear `bot/handlers.py`:
   - `handle_text_message(update, context)` — verificar `chat_id`, dispatch por estado
   - `handle_voice_message(update, context)` — verificar `chat_id`, llamar a voice.py

5. Crear `bot/commands.py`:
   - `/start` → verificar `chat_id`, si es nuevo usuario iniciar onboarding
   - `/status` → placeholder: "próximamente"
   - `/pause [días]` → guardar `pause_until` en DB
   - `/unblock [proyecto]` → placeholder
   - `/delegate` → placeholder

6. En todos los handlers: verificar `update.effective_chat.id == settings.TELEGRAM_USER_ID` como primera línea. Si no coincide, ignorar silenciosamente.

7. Crear `requirements.txt` y deploy en Railway.

### Entregables
- [ ] `/start` responde en Telegram
- [ ] `/pause 3` guarda fecha de pausa en DB
- [ ] Mensajes de chat_id desconocido son ignorados
- [ ] Deploy en Railway funcionando (proceso no duerme)
- [ ] Variables de entorno configuradas en Railway

---

## Fase 2A — Agent: context builder + Groq client (requiere 1A)

**Objetivo:** El agente puede generar una respuesta contextualizada dado el estado de la DB.

### Pasos

1. Instalar dependencias:
   ```
   groq
   SQLAlchemy
   psycopg2-binary
   supabase
   ```

2. Crear `db/models.py` — SQLAlchemy models para todas las tablas del schema.

3. Crear `db/queries.py` — funciones de acceso a DB:
   - `get_user_state(telegram_id)` → user_state row
   - `get_active_projects(user_id)` → lista ordenada por prioridad
   - `get_todays_checkin(user_id, checkin_type)` → checkin row o None
   - `get_open_commitments(user_id)` → compromisos sin cumplir
   - `get_recent_evidence(user_id, days=7)` → evidencia de los últimos N días
   - `get_days_since_movement(project_id)` → int o None
   - `get_open_blockers(user_id)` → bloqueadores sin resolver
   - `create_checkin(user_id, type)` → row o None si ya existe (upsert)
   - `record_evidence(user_id, project_id, description)` → evidence row
   - `create_commitment(user_id, project_id, checkin_id, description)` → commitment row
   - `update_conversation_state(telegram_id, new_state)` → void
   - `set_pause(telegram_id, until_date)` → void

4. Crear `agent/context_builder.py`:
   ```python
   async def build_context(telegram_id: int) -> dict:
       """
       Única función que lee estado del usuario desde DB para el LLM.
       Llamada por todos los jobs y handlers — no duplicar esta lógica.

       Retorna dict con:
         - user_state: conversation_state, is_paused, pause_until
         - projects: lista con campos relevantes + days_since_movement
         - todays_commitments: compromisos del día de hoy
         - recent_evidence: evidencia de los últimos 7 días
         - open_blockers: bloqueadores activos
         - open_delegations: delegaciones sin cerrar
       """
   ```

   **IMPORTANTE:** Wrap todo el body en try/except. Si la DB falla:
   ```python
   except Exception as e:
       logger.error(f"context_builder failed: {e}")
       raise  # el caller maneja y notifica al usuario por Telegram
   ```

5. Crear `agent/groq_client.py`:
   ```python
   from groq import Groq

   client = Groq(api_key=settings.GROQ_API_KEY)

   async def generate_response(
       system_prompt: str,
       user_message: str,
       max_tokens: int = 500,
       temperature: float = 0.7
   ) -> str:
       """
       Wrapper del Groq SDK. Retorna solo el texto de la respuesta.
       Retry: 2 intentos en timeout/rate limit, luego lanza excepción.
       Respuesta vacía: retorna mensaje de fallback.
       """
   ```

   Errores a manejar explícitamente:
   - `groq.APITimeoutError` → retry 2x con backoff, luego fallback
   - `groq.RateLimitError` → backoff + retry
   - Respuesta vacía → fallback message
   - Cualquier otro error → loggear + fallback

6. Crear `agent/prompt_builder.py`:
   ```python
   def build_prompt(mode: str, context: dict) -> tuple[str, str]:
       """
       Carga template de /prompts/{mode}.txt.
       Inyecta context en el template.
       Retorna (system_prompt, user_message).
       Lanza FileNotFoundError si el template no existe — no swallow.
       """
   ```

7. Crear archivos de prompts en `/prompts/`. El contenido viene del guión de conversación escrito en P0. Estructura base de cada archivo:
   - `system.txt` → identidad del agente (basado en `Vantara.md` sección "Personalidad del agente" y "Prompt operativo base")
   - `morning.txt` → preguntas de priorización + instrucciones de confrontación si detecta mal uso de tiempo
   - `midday.txt` → solicitud de evidencia + corrección si no avanzó
   - `evening.txt` → cierre, lecciones, siguiente paso
   - `weekly.txt` → retrospectiva semanal con métricas reales
   - `onboarding.txt` → entrevista conversacional para capturar proyectos y contexto
   - `confrontation.txt` → template de confrontación por estancamiento (inyectar nombre del proyecto, días sin movimiento)
   - `unblock.txt` → secuencia de preguntas para destrabar

### Entregables
- [ ] `build_context()` retorna dict con todos los campos necesarios
- [ ] `generate_response()` maneja errores de Groq sin crashear
- [ ] `build_prompt()` carga archivos .txt correctamente
- [ ] Test manual: llamar a `build_context()` + `generate_response()` y verificar output

---

## Fase 2B — Voice transcription (requiere 1B, paralelo con 2A)

**Objetivo:** El bot acepta notas de voz y las transcribe antes de procesarlas.

### Pasos

1. Instalar: `openai` (solo para Whisper)

2. Crear `bot/voice.py`:
   ```python
   from openai import OpenAI

   whisper = OpenAI(api_key=settings.OPENAI_API_KEY)

   async def transcribe_voice(file_path: str) -> str | None:
       """
       Transcribe un archivo de audio con Whisper.
       Retorna texto transcripto o None si falla.
       Valida tamaño antes de llamar: si > 25MB, retorna None.
       """
   ```

3. En `bot/handlers.py`, `handle_voice_message()`:
   - Descargar el voice file de Telegram a `/tmp/`
   - Validar tamaño: si > 25MB → responder "El audio es muy largo, escribe el mensaje"
   - Llamar `transcribe_voice(file_path)`
   - Si `None` → responder "No pude transcribir el audio, escribe el mensaje"
   - Si texto → procesar como `handle_text_message()` con el texto transcripto
   - Limpiar archivo temporal después

### Entregables
- [ ] Nota de voz corta → texto transcripto → procesado correctamente
- [ ] Audio > 25MB → mensaje claro al usuario (no timeout)
- [ ] Whisper API error → fallback a "escribe el mensaje"

---

## Fase 3 — Scheduler + check-ins (requiere 2A + 2B)

**Objetivo:** El bot envía check-ins automáticos a los horarios configurados.

### Pasos

1. Crear `scheduler/jobs.py` con los siguientes jobs:

   **`morning_checkin_job(context)`:**
   - Verificar si usuario está en pausa (`pause_until > now`) → skip
   - Verificar si ya se envió check-in hoy (`get_todays_checkin(user_id, 'morning')`) → skip si existe
   - Crear checkin en DB (`create_checkin(user_id, 'morning')`)
   - `build_context()` → `build_prompt('morning', ctx)` → `generate_response()`
   - Enviar mensaje al usuario via `context.bot.send_message(TELEGRAM_USER_ID, text)`
   - Si `build_context()` falla → enviar mensaje de error al usuario

   **`midday_checkin_job(context)`:** misma lógica con tipo 'midday'

   **`evening_checkin_job(context)`:** misma lógica con tipo 'evening'

   **`weekly_retro_job(context)`:** solo correr viernes. Generar retro con métricas de la semana.

   **`stagnation_check_job(context)`:** correr nightly.
   - Para cada proyecto activo, calcular `get_days_since_movement(project_id)`
   - Si > 5 días y usuario no está en pausa → generar confrontación via `build_prompt('confrontation', ctx)` + `generate_response()` → enviar

2. En `main.py`, registrar jobs en `Application.job_queue`:
   ```python
   job_queue = app.job_queue

   # Horarios configurables (leer de user_state.checkin_times)
   job_queue.run_daily(morning_checkin_job, time=time(8, 0))
   job_queue.run_daily(midday_checkin_job, time=time(13, 0))
   job_queue.run_daily(evening_checkin_job, time=time(19, 0))
   job_queue.run_daily(weekly_retro_job, time=time(20, 0), days=(4,))  # viernes
   job_queue.run_daily(stagnation_check_job, time=time(21, 0))
   ```

3. Implementar el flujo completo de onboarding en `bot/handlers.py`:
   - Cuando `conversation_state == 'ONBOARDING_IN_PROGRESS'`, el agente hace preguntas secuenciales
   - Cada respuesta del usuario se guarda en DB (`projects`, `user_state`)
   - Al completar → `update_conversation_state(telegram_id, 'ACTIVE')`
   - Bienvenida: "Listo. Empezamos mañana a las 8am."

4. Implementar flujo de respuesta a check-ins:
   - Cuando `conversation_state == 'ACTIVE'` y hay un checkin de hoy en estado 'pending'
   - La respuesta del usuario se guarda en `checkins.user_response`
   - El agente extrae compromisos del texto y los guarda en `commitments`
   - El agente confirma lo que entendió: "Registré: [lista de compromisos]. ¿Correcto?"

5. Implementar `/status` completo:
   - `build_context()` → formatear tabla de proyectos con estado y días sin movimiento
   - Ejemplo:
     ```
     Zucarlink [P1] — 3 días sin movimiento
     Next: landing terminada

     [Proyecto 2] [P2] — activo ayer
     Next: reunión agendada
     ```

### Entregables
- [ ] Check-in mañanero llega a las 8am
- [ ] No llega check-in duplicado si el proceso se reinicia
- [ ] Respuesta al check-in guarda compromisos en DB
- [ ] `/status` muestra tabla de proyectos
- [ ] Onboarding completo en una sesión guarda proyectos en DB

---

## Fase 4 — Tests + evals (requiere todo lo anterior)

**Objetivo:** Cobertura de los paths críticos y evals de calidad de confrontación.

### Tests a implementar

**`tests/test_context_builder.py`:**
- Usuario sin proyectos → `build_context()` retorna empty projects list
- Proyecto con evidencia reciente → `days_since_movement` correcto
- DB no disponible → lanza excepción (no retorna silenciosamente None)

**`tests/test_commands.py`:**
- `/pause 3` → `pause_until` guardado correctamente en DB
- `/pause 0` → `pause_until` limpiado
- `/status` sin proyectos → mensaje de onboarding
- `/unblock proyecto-inexistente` → mensaje de error

**`tests/test_scheduler_jobs.py`:**
- `morning_checkin_job()` con usuario en pausa → no envía mensaje
- `morning_checkin_job()` con checkin ya existente hoy → no envía duplicado
- `stagnation_check_job()` con proyecto > 5 días → genera confrontación
- `stagnation_check_job()` con usuario en pausa → no confronta

**`tests/evals/confrontation_cases.json`:**
```json
[
  {
    "name": "proyecto estancado 5 dias",
    "context": {
      "project_name": "Zucarlink",
      "days_since_movement": 5,
      "last_commitment": "terminar landing",
      "is_paused": false
    },
    "criteria": [
      "menciona 'Zucarlink' por nombre",
      "menciona '5 días' o número específico",
      "tiene call to action concreto",
      "menos de 60 palabras"
    ]
  }
]
```

Script `tests/evals/run_confrontation_evals.py`:
- Carga casos del JSON
- Para cada caso: `build_prompt('confrontation', ctx)` + `generate_response()`
- Evalúa cada criterio → score
- Imprime reporte: `PASS/FAIL` por criterio + score total

### Entregables
- [ ] `pytest tests/` pasa sin errores
- [ ] Eval de confrontación: score > 80% en casos base
- [ ] Test de dedup: confirmar que el unique constraint previene duplicados

---

## Checklist final pre-uso

- [ ] Guión de conversación escrito (P0)
- [ ] Supabase con schema completo
- [ ] Variables de entorno en Railway: TELEGRAM_TOKEN, TELEGRAM_USER_ID, GROQ_API_KEY, OPENAI_API_KEY, DATABASE_URL
- [ ] Railway Hobby plan activo ($5/mo — no el gratuito)
- [ ] `/start` inicia onboarding correctamente
- [ ] Onboarding completo guarda proyectos en DB
- [ ] Check-in mañanero llega a las 8am
- [ ] Nota de voz se transcribe correctamente
- [ ] `/pause 1` silencia el scheduler
- [ ] `/status` muestra estado actualizado
- [ ] `pytest tests/` pasa
- [ ] Eval de confrontación > 80%

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | ISSUES (4 critical gaps, 1 unresolved) | 4 expansions accepted: quick commands, weekly retro, pattern detection, voice |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES (3 critical gaps, 0 unresolved) | 5 issues: scheduler, voice tool, state storage, dedup jobs, DB error handling |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |

**UNRESOLVED:** 0 — todas las decisiones fueron tomadas.

**CRITICAL GAPS (resolver en implementación):**
1. `checkins` table → unique constraint `(user_id, date, checkin_type)` — ya está en el schema
2. `context_builder.build()` con DB error → raise + notificar por Telegram
3. Voice handler → validar tamaño antes de llamar a Whisper

**VERDICT:** CEO + ENG REVIEWED — listo para implementar. Eng review tiene open issues que son requisitos de implementación, no bloqueantes del plan.
