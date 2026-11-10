"""The report PDF: header (child, class, age, period), the text, the photos the
teacher chose and a signature line."""

import logging
import re
import unicodedata
from datetime import date
from typing import Any

from i18n import Translator
from reports.images import ImageError, pdf_image
from reports.pdf import CONTENT_WIDTH, MARGIN, MUTED, PdfDocument
from reports.prompt import is_title

logger = logging.getLogger(__name__)

PHOTO_COLUMNS = 2
PHOTO_GAP = 16.0  # between photos, in points
PHOTO_MAX_HEIGHT = 200.0
CAPTION_HEIGHT = 14.0


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
    photos: list[tuple[bytes, str]] | None = None,
) -> bytes:
    """`photos`: (image bytes, caption, e.g. the event date), in the chosen order."""
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
        if not paragraph.strip():
            continue
        text = " ".join(paragraph.split())
        if is_title(text):  # section title (when the teacher asked for a structure)
            doc.text(text, size=12, bold=True, space_after=4, keep_with_next=3 * 16.5)
        else:
            doc.text(text, size=11, leading=16.5, space_after=8)
    _photo_section(doc, tr, photos or [])
    doc.signature(tr.t("report_pdf.signature"))
    return doc.render()


def _photo_section(doc: PdfDocument, tr: Translator, photos: list[tuple[bytes, str]]) -> None:
    """The photos, two per row, each with its caption, after the text."""
    images = []
    for data, caption in photos:
        try:
            images.append((pdf_image(data), caption))
        except ImageError as error:
            logger.warning("A photo was left out of the PDF: %s", error)
    if not images:
        return
    column = (CONTENT_WIDTH - PHOTO_GAP * (PHOTO_COLUMNS - 1)) / PHOTO_COLUMNS
    doc.text(tr.t("report_pdf.photos"), size=12, bold=True, space_after=8,
             keep_with_next=PHOTO_MAX_HEIGHT / 2)
    for start in range(0, len(images), PHOTO_COLUMNS):
        row = images[start : start + PHOTO_COLUMNS]
        sizes = [_fit(image.display_size, column, PHOTO_MAX_HEIGHT) for image, _ in row]
        row_height = max(height for _, height in sizes) + CAPTION_HEIGHT
        doc.ensure_space(row_height)
        top = doc.y
        for index, ((image, caption), (width, height)) in enumerate(zip(row, sizes, strict=True)):
            left = MARGIN + index * (column + PHOTO_GAP)
            x = left + (column - width) / 2  # centered in its column
            doc.draw_image(image, x, top - height, width, height)
            if caption:
                doc.draw_text(x, top - height - 11, caption)
        doc.y = top - row_height - 10


def _fit(size: tuple[int, int], max_width: float, max_height: float) -> tuple[float, float]:
    """The photo's size scaled to fit the box, keeping its proportions."""
    width, height = size
    scale = min(max_width / width, max_height / height)
    return width * scale, height * scale
