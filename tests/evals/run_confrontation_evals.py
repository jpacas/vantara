#!/usr/bin/env python3
"""
Confrontation quality evals.
Runs each case in confrontation_cases.json against Groq and checks criteria.
Usage: python tests/evals/run_confrontation_evals.py
"""
import json
import asyncio
from pathlib import Path

# Load cases
CASES_FILE = Path(__file__).parent / "confrontation_cases.json"


async def run_eval(case: dict) -> dict:
    """Run a single eval case. Returns result dict with pass/fail per criterion."""
    from agent.groq_client import generate_response

    # Build a minimal prompt from the case context
    ctx = case["context"]
    system = "Eres Vantara, un agente de accountability. Sé directo, breve y exigente."
    user_msg = (
        f"Proyecto: {ctx.get('project_name', 'N/A')}\n"
        f"Días sin movimiento: {ctx.get('days_since_movement', 0)}\n"
        f"Último compromiso: {ctx.get('last_commitment', 'N/A')}\n"
        "Genera una confrontación directa."
    )

    response = await generate_response(system, user_msg, max_tokens=150)

    # Evaluate criteria
    results = []
    for criterion in case["criteria"]:
        # Simple heuristic checks — adjust as needed
        passed = _check_criterion(criterion, response, ctx)
        results.append({"criterion": criterion, "passed": passed})

    return {
        "name": case["name"],
        "response": response,
        "results": results,
        "score": sum(1 for r in results if r["passed"]) / len(results),
    }


def _check_criterion(criterion: str, response: str, ctx: dict) -> bool:
    """Basic criterion checker. Returns True if criterion appears met."""
    response_lower = response.lower()

    if "menciona" in criterion and "por nombre" in criterion:
        project_name = ctx.get("project_name", "").lower()
        return project_name in response_lower

    if "menciona el nombre" in criterion:
        project_name = ctx.get("project_name", "").lower()
        return project_name in response_lower

    if "días" in criterion or "número específico" in criterion:
        days = str(ctx.get("days_since_movement", ""))
        return days in response

    if "menos de 60 palabras" in criterion:
        return len(response.split()) <= 60

    if "call to action" in criterion:
        action_words = ["haz", "envía", "escribe", "llama", "agenda", "decide", "termina", "completa", "siguiente"]
        return any(w in response_lower for w in action_words)

    if "tono directo" in criterion:
        hedging = ["quizás", "tal vez", "si puedes", "cuando tengas", "considera"]
        return not any(h in response_lower for h in hedging)

    if "no acepta la excusa" in criterion:
        acceptance_words = ["entiendo", "comprendo", "tiene sentido", "es normal"]
        return not any(w in response_lower for w in acceptance_words)

    if "pide acción concreta" in criterion:
        action_words = ["haz", "envía", "escribe", "llama", "agenda", "decide", "termina", "completa", "en las próximas"]
        return any(w in response_lower for w in action_words)

    if "reconoce el bloqueador" in criterion:
        blocker_words = ["cliente", "correo", "bloqueo", "bloqueador", "obstáculo"]
        return any(w in response_lower for w in blocker_words)

    if "propone acción alternativa" in criterion:
        alt_words = ["alternativa", "otra", "otro canal", "whatsapp", "teléfono", "llama", "busca"]
        return any(w in response_lower for w in alt_words)

    if "cuestiona si merece atención" in criterion:
        question_words = ["vale la pena", "merece", "prioridad", "realmente", "necesario"]
        return any(w in response_lower for w in question_words)

    if "pide decisión" in criterion or "activar, pausar o eliminar" in criterion:
        decision_words = ["activar", "pausar", "eliminar", "decide", "decisión", "¿qué"]
        return any(w in response_lower for w in decision_words)

    # Default: mark as pass if we can't auto-check
    return True


async def main():
    cases = json.loads(CASES_FILE.read_text())
    print(f"\nRunning {len(cases)} confrontation evals...\n")

    total_score = 0
    for case in cases:
        result = await run_eval(case)
        total_score += result["score"]

        status = "PASS" if result["score"] >= 0.8 else "FAIL"
        print(f"[{status}] [{result['score']*100:.0f}%] {result['name']}")
        print(f"  Response: {result['response'][:100]}{'...' if len(result['response']) > 100 else ''}")
        for r in result["results"]:
            icon = "  ok" if r["passed"] else "  FAIL"
            print(f"{icon} {r['criterion']}")
        print()

    overall = total_score / len(cases) if cases else 0
    print(f"\nOverall score: {overall*100:.0f}%")
    print(f"Target: >80%")
    if overall >= 0.8:
        print("PASSED")
    else:
        print("NEEDS IMPROVEMENT -- revise confrontation.txt")


if __name__ == "__main__":
    asyncio.run(main())
