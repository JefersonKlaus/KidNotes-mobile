"""Writes one report draft: events of the period → prompt → Groq → checked, clean text."""

import logging
from datetime import date
from typing import Any

from i18n import Translator
from reports.ai import ReportAIError
from reports.prompt import build_prompt, clean_answer, ground_answer, source_count

logger = logging.getLogger(__name__)


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
    instructions: str = "",
) -> str:
    """The report text, with the child's real first name put back (on the device).

    `instructions`: the teacher's instructions for the report (structure,
    standards...); they shape the text but never allow inventing.
    """
    system, user, names = build_prompt(
        tr, student, events, period_start, period_end, classmates, instructions
    )
    answer = await client.complete(system, user)
    sources = source_count(student, events)
    grounding = ground_answer(
        clean_answer(answer), sources, allow_titles=bool(instructions.strip())
    )
    # Logs carry counts and ids only: the text is about the child.
    if not grounding.checked:
        logger.warning(
            "Report for student %s: the AI cited no sources, so its text could not be "
            "checked against the records. Review it carefully.", student["id"],
        )
    if grounding.removed or grounding.unknown_sources:
        logger.warning(
            "Report for student %s: removed %d paragraph(s) not based on the %d source(s)%s.",
            student["id"], len(grounding.removed), sources,
            f"; the AI cited sources that don't exist: {sorted(grounding.unknown_sources)}"
            if grounding.unknown_sources else "",
        )
    if grounding.kept == 0:
        raise ReportAIError("ungrounded", "no paragraph of the answer was based on the sources")
    logger.info("Report for student %s: %d paragraph(s) based on %d source(s).",
                student["id"], grounding.kept, sources)
    return names.restore(grounding.text)
