# TODOS — Vantara

## P0 — Antes de implementar

### Guión de conversación del onboarding
**What:** Escribir a mano 10-15 mensajes de ejemplo de cómo debe sonar el bot en la primera semana.
**Why:** El tono y brevedad del bot es el producto. Sin un guión escrito primero, el prompt base va a sonar genérico y el bot perderá credibilidad en los primeros días.
**Pros:** Define el prompt base del agente, el tono de confrontación, y el largo máximo de mensajes antes de tocar código.
**Cons:** Requiere 2-3 horas de escritura manual.
**Context:** Escribir ejemplos concretos: "¿Cuáles son tus 3 prioridades reales de hoy?" → respuesta del usuario → reacción del bot si la priorización es mala. También: cómo suena la confrontación de un proyecto estancado. Cuántas líneas máximo por mensaje.
**Effort:** S (human: 2-3h / CC: irrelevante — esto es trabajo tuyo)
**Depends on:** Nada. Hacer primero.

---

## P1 — Durante implementación

### Dedup de check-ins en scheduler
**What:** Unique constraint `(user_id, date, checkin_type)` en tabla `checkins` + verificación pre-envío.
**Why:** Si Railway reinicia el proceso justo cuando el scheduler está a punto de disparar, puede enviar el mismo check-in dos veces. Recibir el mismo mensaje dos veces destruye la credibilidad instantáneamente.
**Pros:** Previene duplicados con cero costo en UX.
**Cons:** Ninguno — el constraint es trivial.
**Context:** Agregar al schema desde el inicio. En el job, antes de enviar: `SELECT id FROM checkins WHERE user_id=? AND date=today AND type=?`. Si existe, skip.
**Effort:** S (human: 1h / CC: 10 min)
**Depends on:** DB schema (Phase 1A).

### DB connection error handling en context_builder
**What:** Si la DB no está disponible, notificar al usuario por Telegram en lugar de crashear silenciosamente.
**Why:** Un crash silencioso significa check-ins que nunca llegan y el usuario no sabe por qué el bot dejó de funcionar.
**Pros:** Visibilidad de fallos sin tener que revisar logs de Railway.
**Cons:** Requiere un fallback que funcione sin DB (send_message directo sin context).
**Context:** Wrap `build_context()` en try/except. En el except, usar el bot para enviar: "Tuve un problema técnico. Intento de nuevo en 5 minutos." Log el error a Railway logs.
**Effort:** S (human: 1h / CC: 15 min)
**Depends on:** context_builder.py implementado.

### Evals de confrontación
**What:** 10-15 pares (contexto_del_proyecto, respuesta_esperada_del_bot) para validar calidad de confrontación.
**Why:** Un unit test no puede validar si "Ese proyecto lleva 5 días sin moverse" suena apropiado. Sin evals, cada cambio de prompt es un shot in the dark.
**Pros:** Base para iterar prompts con confianza. Detecta regresiones de calidad.
**Cons:** Requiere escribir los casos a mano — no se puede generar automáticamente.
**Context:** Archivo `tests/evals/confrontation_cases.json`. Script que corre cada caso contra Groq (llama-3.3-70b-versatile) y reporta si la respuesta cumple criterios: ¿menciona el proyecto por nombre? ¿está bajo el límite de N palabras? ¿tiene un call to action concreto?
**Effort:** S (human: 1-2 días / CC: 30 min)
**Depends on:** Guión de conversación completado (P0). Prompts base escritos.

---

## P2 — Después de 30 días de uso

### Detección de patrones personales
**What:** Análisis de historial para identificar en qué días/horarios el cumplimiento es más bajo, qué proyectos se evitan sistemáticamente.
**Why:** Hace la confrontación más inteligente: "Los lunes en la tarde históricamente no avanzas en este proyecto."
**Pros:** Confrontación con datos reales > confrontación genérica.
**Cons:** Requiere suficientes datos para ser útil. Si los datos son escasos, los insights son incorrectos.
**Context:** Solo tiene sentido después de 30 días de uso activo. Query semanal sobre checkins + evidence para identificar patrones. Pasar insights al context_builder.
**Effort:** M (human: 3-5 días / CC: 1h)
**Depends on:** 30 días de uso activo + data en DB.

---

## Deferred (from CEO review)

- **Dashboard web visual** — Fase 2. El valor está en Telegram.
- **Integración con calendario** — Fase 4. Complejidad sin beneficio claro en MVP.
- **Multi-usuario** — Solo si decide productizar. Requiere refactor de autenticación.
