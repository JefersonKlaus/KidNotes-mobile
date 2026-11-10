"""Report screens.

- ReportScreen: choose the period and the students, optionally write
  instructions for the AI (structure, standards...), then generate one report
  per student (AI draft from the events of the period). Lists the reports
  already generated for the class, grouped by month (open or delete them).
  The Groq API key is set in Settings (screens/settings.py).
- ReportReviewScreen: review/edit the draft, add images from the child's
  events (see report_photos.py), save the text, generate the PDF (and share
  it, on phones).
- DeleteReportDialog: confirmation before deleting a saved report.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import flet as ft

from components import (
    bottom_action_bar,
    field_border,
    page_header,
    photo,
    safe_update,
    section_title,
)
from database.settings import REPORT_INSTRUCTIONS_MAX_LENGTH
from dates import to_local_date
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)

DEFAULT_PERIOD_DAYS = 182  # about a school semester


@dataclass
class ReportRequest:
    """What the teacher chose on the report screen, and the generation progress."""

    class_id: str
    start: date = field(default_factory=lambda: date.today() - timedelta(days=DEFAULT_PERIOD_DAYS))
    end: date = field(default_factory=date.today)
    student_ids: set[str] = field(default_factory=set)
    # student id -> (status, detail): waiting | generating | done (report id) |
    # no_events | error (error code)
    statuses: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    running: bool = False
    error: str | None = None
    # Months ("2025-07") whose saved reports are shown; None: only the latest month.
    expanded_months: set[str] | None = None
    # The teacher's instructions for the AI (structure, standards, sections...).
    instructions: str = ""


class ReportScreen:
    def __init__(
        self,
        request: ReportRequest,
        class_data: dict[str, Any],
        students: list[dict[str, Any]],
        event_counts: dict[str, int],
        saved_reports: list[dict[str, Any]],
        student_names: dict[str, str],
        has_api_key: bool,
        tr: Translator,
        page: ft.Page,
        on_back: Any,
        on_period_change: Any,
        on_generate: Any,
        on_open_settings: Any,
        on_open_report: Any,
        on_save_instructions: Any = None,
        on_delete_report: Any = None,
    ) -> None:
        self.request = request
        self.class_data = class_data
        self.students = students
        self.event_counts = event_counts
        self.saved_reports = saved_reports
        self.student_names = student_names
        self.has_api_key = has_api_key
        self.tr = tr
        self.page = page
        self.on_back = on_back
        self.on_period_change = on_period_change
        self.on_generate = on_generate
        self.on_open_settings = on_open_settings
        self.on_open_report = on_open_report
        self.on_save_instructions = on_save_instructions
        self.on_delete_report = on_delete_report
        self.chips: dict[str, ft.Chip] = {}
        self.class_chip: ft.Chip | None = None
        self.month_groups: dict[str, tuple[ft.Container, ft.Column]] = {}
        self.instructions_field: ft.TextField | None = None
        self.date_picker: ft.DatePicker | None = None

    # --- layout ------------------------------------------------------------------------

    def build(self) -> ft.Column:
        controls: list[ft.Control] = [
            section_title(self.tr.t("reports.period"), ft.Icons.DATE_RANGE),
            self._period_row(),
            section_title(self.tr.t("reports.students"), ft.Icons.CHILD_CARE),
            self._students_chips(),
            section_title(self.tr.t("reports.instructions"), ft.Icons.EDIT_NOTE),
            self._instructions_field(),
            *([] if self.has_api_key else [self._api_key_missing()]),
            self._privacy_notice(),
        ]
        if self.request.error:
            controls.append(ft.Text(self.request.error, color=ft.Colors.ERROR, size=13))
        if self.request.statuses:
            controls += [
                self._status_row(sid, status) for sid, status in self.request.statuses.items()
            ]
        controls += [
            section_title(self.tr.t("reports.saved_title"), ft.Icons.DESCRIPTION_OUTLINED),
            *(
                self._saved_groups()
                or [ft.Text(self.tr.t("reports.none_yet"), size=13, color=COLORS["muted"])]
            ),
        ]
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.tr.t("reports.title"),
                        self.class_data["name"],
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=controls,
                        spacing=14,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        bar = bottom_action_bar(
            self.tr.t("reports.generate"), ft.Icons.AUTO_AWESOME, self.on_generate
        )
        bar.content.controls[0].disabled = self.request.running
        return bar

    def _period_row(self) -> ft.Row:
        return ft.Row(
            controls=[
                self._date_field("reports.from", self.request.start, "start"),
                self._date_field("reports.to", self.request.end, "end"),
            ],
            spacing=10,
        )

    def _date_field(self, label: str, value: date, which: str) -> ft.TextField:
        return ft.TextField(
            label=self.tr.t(label),
            value=self.tr.format_date(value),
            read_only=True,
            expand=True,
            prefix_icon=ft.Icons.EVENT,
            border=field_border(),
            bgcolor=COLORS["surface"],
            on_click=lambda _: self.open_date_picker(which),
        )

    def _instructions_field(self) -> ft.TextField:
        """Free text the AI follows for the form of the report (never its content)."""
        self.instructions_field = ft.TextField(
            value=self.request.instructions,
            multiline=True,
            min_lines=3,
            max_lines=10,
            max_length=REPORT_INSTRUCTIONS_MAX_LENGTH,
            capitalization=ft.TextCapitalization.SENTENCES,
            hint_text=self.tr.t("reports.instructions_hint"),
            helper=self.tr.t("reports.instructions_help"),
            border=field_border(focused_color=COLORS["primary"]),
            bgcolor=COLORS["surface"],
            disabled=self.request.running,
            on_change=self._on_instructions_change,
            on_blur=lambda _: self.save_instructions(),
        )
        return self.instructions_field

    def _on_instructions_change(self, event: Any) -> None:
        self.request.instructions = event.control.value or ""

    def save_instructions(self) -> None:
        if self.on_save_instructions is not None:
            self.on_save_instructions(self.request.instructions)

    def _style_chip(self, chip: ft.Chip) -> None:
        chip.label.color = ft.Colors.WHITE if chip.selected else COLORS["ink"]
        chip.label.weight = ft.FontWeight.W_700 if chip.selected else ft.FontWeight.NORMAL

    def _students_chips(self) -> ft.Row:
        self.chips = {}
        for student in self.students:
            count = self.event_counts.get(student["id"], 0)
            self.chips[student["id"]] = ft.Chip(
                label=ft.Text(f"{student['name']} ({count})"),
                selected=student["id"] in self.request.student_ids,
                show_checkmark=True,
                selected_color=COLORS["primary"],
                check_color=ft.Colors.WHITE,
                on_select=lambda _, sid=student["id"]: self.toggle_student(sid),
            )
        self.class_chip = ft.Chip(
            label=ft.Text(self.tr.t("event_form.whole_class")),
            leading=ft.Icon(ft.Icons.GROUPS, size=18),
            selected=self._all_selected(),
            show_checkmark=True,
            selected_color=COLORS["primary"],
            check_color=ft.Colors.WHITE,
            border_side=ft.BorderSide(1, COLORS["primary"]),
            on_select=lambda _: self.toggle_whole_class(),
        )
        for chip in [*self.chips.values(), self.class_chip]:
            self._style_chip(chip)
        return ft.Row(
            controls=[*self.chips.values(), self.class_chip], wrap=True, spacing=8, run_spacing=8
        )

    def _api_key_missing(self) -> ft.Container:
        """No Groq key yet: it is set in Settings."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY, color=COLORS["primary"], size=20),
                    ft.Text(self.tr.t("reports.api_key_missing"), size=13, color=COLORS["ink"],
                            expand=True),
                    ft.TextButton(self.tr.t("menu.settings"), icon=ft.Icons.SETTINGS_OUTLINED,
                                  on_click=lambda _: self.on_open_settings()),
                ],
                spacing=10,
            ),
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=14,
            padding=ft.Padding(left=12, right=4, top=6, bottom=6),
            data="api-key-missing",
        )

    def _privacy_notice(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PRIVACY_TIP_OUTLINED, color=COLORS["primary"], size=20),
                    ft.Text(
                        self.tr.t("reports.privacy"), size=12, color=COLORS["ink"], expand=True
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLORS["lavender"],
            border_radius=14,
            padding=12,
        )

    def _status_row(self, student_id: str, status: tuple[str, str | None]) -> ft.Container:
        state, detail = status
        name = self.student_names.get(student_id, "?")
        if state == "generating":
            icon: ft.Control = ft.ProgressRing(width=18, height=18, stroke_width=2)
        else:
            icon = ft.Icon(
                {
                    "waiting": ft.Icons.HOURGLASS_EMPTY,
                    "done": ft.Icons.CHECK_CIRCLE,
                    "no_events": ft.Icons.INFO_OUTLINE,
                    "error": ft.Icons.ERROR_OUTLINE,
                }[state],
                size=18,
                color=ft.Colors.ERROR if state == "error" else COLORS["primary"],
            )
        message = self.tr.t(
            f"reports.status.error.{detail}" if state == "error" else f"reports.status.{state}"
        )
        return ft.Container(
            content=ft.Row(
                controls=[
                    icon,
                    ft.Column(
                        controls=[
                            ft.Text(name, size=14, weight=ft.FontWeight.W_700, color=COLORS["ink"]),
                            ft.Text(
                                message,
                                size=12,
                                color=ft.Colors.ERROR if state == "error" else COLORS["muted"],
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    *(
                        [ft.FilledButton(self.tr.t("reports.open"),
                                         on_click=lambda _: self.on_open_report(detail))]
                        if state == "done"
                        else []
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=14,
            padding=10,
            data=f"status:{student_id}",
        )

    # --- saved reports, grouped by month --------------------------------------------------

    def _saved_groups(self) -> list[ft.Control]:
        """One group per month the reports were generated in, newest first."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for report in self.saved_reports:  # already newest first
            created = to_local_date(report["created_at"])
            key = f"{created.year:04d}-{created.month:02d}" if created else "?"
            groups.setdefault(key, []).append(report)
        expanded = self._expanded_months(list(groups))
        self.month_groups = {}
        controls: list[ft.Control] = []
        for key, reports in groups.items():
            is_open = key in expanded
            rows = ft.Column(controls=[self._saved_row(r) for r in reports], spacing=10,
                             visible=is_open)
            header = self._month_header(key, len(reports), is_open)
            self.month_groups[key] = (header, rows)
            controls.append(ft.Column(controls=[header, rows], spacing=10,
                                      data=f"month:{key}"))
        return controls

    def _expanded_months(self, keys: list[str]) -> set[str]:
        if self.request.expanded_months is None:  # default: only the latest month
            self.request.expanded_months = set(keys[:1])
        return self.request.expanded_months

    def _month_title(self, key: str) -> str:
        year, _, month = key.partition("-")
        if not month:
            return key
        return self.tr.format_month(date(int(year), int(month), 1))

    def _month_header(self, key: str, count: int, is_open: bool) -> ft.Container:
        """Tap to show or hide the reports of the month."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EXPAND_MORE if is_open else ft.Icons.CHEVRON_RIGHT,
                            color=COLORS["primary"]),
                    ft.Text(self._month_title(key), size=15, weight=ft.FontWeight.W_700,
                            color=COLORS["ink"], expand=True),
                    ft.Container(
                        content=ft.Text(str(count), size=12, weight=ft.FontWeight.W_700,
                                        color=COLORS["primary"]),
                        bgcolor=COLORS["lavender"],
                        border_radius=10,
                        padding=ft.Padding(left=8, right=8, top=2, bottom=2),
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=4, right=8, top=8, bottom=8),
            border_radius=10,
            on_click=lambda _, k=key: self.toggle_month(k),
            data=f"month-header:{key}",
        )

    def toggle_month(self, key: str) -> None:
        """Show/hide a month's reports, in place (the page doesn't move)."""
        expanded = self.request.expanded_months
        if expanded is None:
            expanded = self.request.expanded_months = set()
        if key in expanded:
            expanded.discard(key)
        else:
            expanded.add(key)
        header, rows = self.month_groups[key]
        rows.visible = key in expanded
        header.content.controls[0].icon = (
            ft.Icons.EXPAND_MORE if rows.visible else ft.Icons.CHEVRON_RIGHT
        )
        safe_update(rows)
        safe_update(header)

    def _saved_row(self, report: dict[str, Any]) -> ft.Container:
        created = to_local_date(report["created_at"])
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=20, color=COLORS["primary"]),
                    ft.Column(
                        controls=[
                            ft.Text(
                                self.student_names.get(report["student_id"], "?"),
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=COLORS["ink"],
                            ),
                            ft.Text(
                                self.tr.t(
                                    "reports.saved_item",
                                    start=self.tr.format_date(report["period_start"]),
                                    end=self.tr.format_date(report["period_end"]),
                                    date=self.tr.format_date(created) if created else "",
                                ),
                                size=12,
                                color=COLORS["muted"],
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    *(
                        [
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=ft.Colors.ERROR,
                                tooltip=self.tr.t("reports.delete"),
                                # Not while generating: a status line may point to it.
                                disabled=self.request.running,
                                on_click=lambda _: self.on_delete_report(report),
                                data=f"delete:{report['id']}",
                            )
                        ]
                        if self.on_delete_report is not None
                        else []
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=COLORS["muted"]),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=14,
            padding=10,
            on_click=lambda _: self.on_open_report(report["id"]),
            data=f"report:{report['id']}",
        )

    # --- interactions --------------------------------------------------------------------

    def toggle_student(self, student_id: str) -> None:
        if student_id in self.request.student_ids:
            self.request.student_ids.discard(student_id)
        else:
            self.request.student_ids.add(student_id)
        self._refresh_chips()

    def _all_selected(self) -> bool:
        ids = {s["id"] for s in self.students}
        return bool(ids) and ids <= self.request.student_ids

    def toggle_whole_class(self) -> None:
        all_selected = self._all_selected()
        self.request.student_ids = set() if all_selected else {s["id"] for s in self.students}
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        for student_id, chip in self.chips.items():
            chip.selected = student_id in self.request.student_ids
            self._style_chip(chip)
            safe_update(chip)
        if self.class_chip is not None:
            self.class_chip.selected = self._all_selected()
            self._style_chip(self.class_chip)
            safe_update(self.class_chip)

    def open_date_picker(self, which: str) -> None:
        current = self.request.start if which == "start" else self.request.end
        self.date_picker = ft.DatePicker(
            value=current,
            first_date=date(2000, 1, 1),
            last_date=date.today() + timedelta(days=366),
            help_text=self.tr.t("reports.from" if which == "start" else "reports.to"),
            on_change=lambda e: self._on_date_picked(which, e),
        )
        self.page.show_dialog(self.date_picker)

    def _on_date_picked(self, which: str, event: Any) -> None:
        value = getattr(event, "data", None)
        if value is None and self.date_picker is not None:
            value = self.date_picker.value
        picked = to_local_date(value)
        if picked is None:
            return
        start = picked if which == "start" else self.request.start
        end = picked if which == "end" else self.request.end
        self.on_period_change(start, end)  # re-renders: event counts depend on the period



class ReportReviewScreen:
    def __init__(
        self,
        report: dict[str, Any],
        student_name: str,
        draft: str,
        tr: Translator,
        can_share: bool,
        on_change: Any,
        on_save_pdf: Any,
        on_share_pdf: Any,
        on_back: Any,
        on_save_text: Any = None,
        photos: list[tuple[str, bytes | None]] | None = None,
        on_add_photos: Any = None,
        on_remove_photo: Any = None,
    ) -> None:
        self.report = report
        self.student_name = student_name
        self.draft = draft
        self.tr = tr
        self.can_share = can_share
        self.on_change = on_change
        self.on_save_pdf = on_save_pdf
        self.on_share_pdf = on_share_pdf
        self.on_back = on_back
        self.on_save_text = on_save_text
        self.photos = photos or []  # (photo id, bytes or None if unavailable), in order
        self.on_add_photos = on_add_photos
        self.on_remove_photo = on_remove_photo
        self.field: ft.TextField | None = None

    def build(self) -> ft.Column:
        self.field = ft.TextField(
            value=self.draft,
            multiline=True,
            min_lines=14,
            capitalization=ft.TextCapitalization.SENTENCES,
            border=field_border(focused_color=COLORS["primary"]),
            bgcolor=COLORS["surface"],
            text_size=15,
            on_change=lambda e: self.on_change(e.control.value or ""),
        )
        period = self.tr.t(
            "report_review.period",
            start=self.tr.format_date(self.report["period_start"]),
            end=self.tr.format_date(self.report["period_end"]),
        )
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=page_header(
                                    self.tr.t("report_review.title"),
                                    self.student_name,
                                    on_back=lambda _: self.on_back(),
                                    back_tooltip=self.tr.t("common.back"),
                                ),
                                expand=True,
                            ),
                            # Phones: send the PDF (WhatsApp, e-mail, Drive...).
                            ft.OutlinedIconButton(
                                icon=ft.Icons.SHARE,
                                tooltip=self.tr.t("report_review.share_pdf"),
                                on_click=self.on_share_pdf,
                                visible=self.can_share,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(period, size=13, color=COLORS["muted"]),
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.AUTO_AWESOME, size=18,
                                                color=COLORS["primary"]),
                                        ft.Text(self.tr.t("report_review.notice"), size=12,
                                                color=COLORS["ink"], expand=True),
                                    ],
                                    spacing=8,
                                ),
                                bgcolor=COLORS["lavender"],
                                border_radius=14,
                                padding=12,
                            ),
                            self.field,
                            *self._photos_section(),
                        ],
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def _photos_section(self) -> list[ft.Control]:
        """Thumbnails of the chosen photos (each with ✕) and "Add images"."""
        if self.on_add_photos is None:
            return []
        controls: list[ft.Control] = [
            section_title(
                f"{self.tr.t('report_review.photos_title')} ({len(self.photos)})",
                ft.Icons.PHOTO_LIBRARY_OUTLINED,
            ),
            ft.Text(self.tr.t("report_review.photos_hint"), size=12, color=COLORS["muted"]),
        ]
        if self.photos:
            controls.append(
                ft.Row(controls=[self._thumbnail(pid, data) for pid, data in self.photos],
                       wrap=True, spacing=8, run_spacing=8)
            )
        controls.append(
            ft.OutlinedButton(
                self.tr.t("report_review.add_photos"),
                icon=ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED,
                on_click=lambda _: self.on_add_photos(),
                height=48,
            )
        )
        return controls

    def _thumbnail(self, photo_id: str, data: bytes | None) -> ft.Stack:
        return ft.Stack(
            controls=[
                photo(data, self.tr.t("report_review.photo_unavailable"), width=96, height=96),
                ft.Container(
                    content=ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=16,
                        tooltip=self.tr.t("report_review.remove_photo"),
                        on_click=lambda _, pid=photo_id: self.on_remove_photo(pid),
                        data=f"remove-photo:{photo_id}",
                    ),
                    bgcolor=ft.Colors.WHITE,
                    border_radius=20,
                    width=32,
                    height=32,
                    alignment=ft.Alignment.CENTER,
                    top=4,
                    right=4,
                ),
            ],
            width=96,
            height=96,
        )

    def bottom_bar(self) -> ft.Control:
        """Save the text (left) and generate the PDF (right), side by side."""
        return bottom_action_bar(
            self.tr.t("report_review.generate_pdf"),
            ft.Icons.PICTURE_AS_PDF,
            self.on_save_pdf,
            secondary=(
                self.tr.t("report_review.save_text"),
                ft.Icons.SAVE_OUTLINED,
                lambda _: self.on_save_text(),
            ),
        )

    def show_error(self, message: str | None) -> None:
        if self.field is not None:
            self.field.error = message
            safe_update(self.field)


class DeleteReportDialog:
    """Confirmation before deleting a saved report (it can't be undone)."""

    def __init__(
        self,
        repository: Any,
        tr: Translator,
        report: dict[str, Any],
        student_name: str,
        on_deleted: Any,
        on_cancel: Any,
    ) -> None:
        self.repository = repository
        self.tr = tr
        self.report = report
        self.student_name = student_name
        self.on_deleted = on_deleted
        self.on_cancel = on_cancel
        self.error_text: ft.Text | None = None

    def build(self) -> ft.AlertDialog:
        self.error_text = ft.Text("", color=ft.Colors.ERROR, size=13, visible=False)
        message = self.tr.t(
            "delete_report.message",
            name=self.student_name,
            start=self.tr.format_date(self.report["period_start"]),
            end=self.tr.format_date(self.report["period_end"]),
        )
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.t("delete_report.title")),
            content=ft.Column(controls=[ft.Text(message), self.error_text], tight=True, spacing=8),
            actions=[
                ft.TextButton(self.tr.t("common.cancel"), on_click=lambda _: self.on_cancel()),
                ft.FilledButton(
                    self.tr.t("delete_report.confirm"),
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=self.confirm,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def confirm(self, _: Any = None) -> None:
        try:
            self.repository.delete(self.report["id"])
        except Exception:
            logger.exception("Could not delete the report.")
            assert self.error_text is not None
            self.error_text.value = self.tr.t("delete_report.error")
            self.error_text.visible = True
            safe_update(self.error_text)
            return
        self.on_deleted(self.report)
