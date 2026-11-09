"""The report PDF: header (child, class, age, period), the text and a signature line."""

import re
import unicodedata
from datetime import date
from typing import Any

from i18n import Translator
from reports.pdf import MUTED, PdfDocument


def report_filename(student: dict[str, Any], report: dict[str, Any]) -> str:
    """e.g. relatorio-clara-souza-2025-02-01-2025-06-30.pdf (no accents or spaces)."""
    ascii_name = unicodedata.normalize("NFKD", student["name"]).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "student"
    return (
        f"relatorio-{slug}-{report['period_start'].isoformat()}-"
        f"{report['period_end'].isoformat()}.pdf"
    )


def build_report_pdf(
    tr: Translator,
    student: dict[str, Any],
    class_name: str,
    report: dict[str, Any],
    issued_on: date | None = None,
) -> bytes:
    start, end = report["period_start"], report["period_end"]
    doc = PdfDocument(
        title=f"{tr.t('report_pdf.title')} - {student['name']}",
        footer=tr.t("report_pdf.footer"),
    )
    doc.text(tr.t("report_pdf.title"), size=17, bold=True, space_after=4)
    doc.text(student["name"], size=14, bold=True, space_after=2)
    details = [tr.t("report_pdf.class", name=class_name)]
    if student.get("birth_date"):
        details.append(tr.t("report_pdf.age", age=tr.format_age(student["birth_date"], end)))
    doc.text("   ·   ".join(details), size=10, color=MUTED)
    doc.text(
        tr.t("report_pdf.period", start=tr.format_date(start), end=tr.format_date(end)),
        size=10,
        color=MUTED,
    )
    doc.text(
        tr.t("report_pdf.issued", date=tr.format_date(issued_on or date.today())),
        size=10,
        color=MUTED,
    )
    doc.rule()
    for paragraph in re.split(r"\n\s*\n", report["text"].strip()):
        if paragraph.strip():
            doc.text(" ".join(paragraph.split()), size=11, leading=16.5, space_after=8)
    doc.signature(tr.t("report_pdf.signature"))
    return doc.render()
