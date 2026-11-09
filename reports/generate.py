"""Writes one report draft: events of the period → prompt → Groq → clean text."""

from datetime import date
from typing import Any

from i18n import Translator
from reports.prompt import build_prompt, clean_answer


def events_in_period(events: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    return [e for e in events if start <= e["occurred_on"] <= end]


async def write_report(
    client: Any,
    tr: Translator,
    student: dict[str, Any],
    events: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    classmates: list[str],
) -> str:
    """The report text, with the child's real first name put back (on the device)."""
    system, user, names = build_prompt(tr, student, events, period_start, period_end, classmates)
    answer = await client.complete(system, user)
    return names.restore(clean_answer(answer))
