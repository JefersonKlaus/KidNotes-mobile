"""Report screens.

- ReportScreen: choose the period and the students, then generate one report
  per student (AI draft from the events of the period). Lists the reports
  already generated for the class.
- ReportReviewScreen: review/edit the draft, then save or share the PDF.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import flet as ft

from components import bottom_action_bar, page_header, safe_update, section_title
from dates import to_local_date
from i18n import Translator
from theme import COLORS

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
    editing_key: bool = False


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
        on_save_key: Any,
        on_change_key: Any,
        on_open_report: Any,
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
        self.on_save_key = on_save_key
        self.on_change_key = on_change_key
        self.on_open_report = on_open_report
        self.chips: dict[str, ft.Chip] = {}
        self.class_chip: ft.Chip | None = None
        self.key_field: ft.TextField | None = None
        self.date_picker: ft.DatePicker | None = None

    # --- layout ------------------------------------------------------------------------

    def build(self) -> ft.Column:
        controls: list[ft.Control] = [
            section_title(self.tr.t("reports.period"), ft.Icons.DATE_RANGE),
            self._period_row(),
            section_title(self.tr.t("reports.students"), ft.Icons.CHILD_CARE),
            self._students_chips(),
            self._api_key_section(),
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
                [self._saved_row(r) for r in self.saved_reports]
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
            border_radius=14,
            border_color=COLORS["border"],
            bgcolor=COLORS["surface"],
            on_click=lambda _: self.open_date_picker(which),
        )

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

    def _api_key_section(self) -> ft.Control:
        if self.has_api_key and not self.request.editing_key:
            return ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY, size=18, color=COLORS["primary"]),
                    ft.Text(
                        self.tr.t("reports.api_key_configured"),
                        size=13,
                        color=COLORS["muted"],
                        expand=True,
                    ),
                    ft.TextButton(
                        self.tr.t("reports.api_key_change"),
                        on_click=lambda _: self.on_change_key(),
                    ),
                ],
                spacing=8,
            )
        self.key_field = ft.TextField(
            label=self.tr.t("reports.api_key"),
            password=True,
            can_reveal_password=True,
            autocorrect=False,
            enable_suggestions=False,
            helper=self.tr.t("reports.api_key_help"),
            border_radius=14,
            border_color=COLORS["border"],
            bgcolor=COLORS["surface"],
            expand=True,
        )
        return ft.Column(
            controls=[
                self.key_field,
                ft.Row(
                    controls=[
                        ft.OutlinedButton(
                            self.tr.t("reports.api_key_save"),
                            icon=ft.Icons.KEY,
                            on_click=self.save_key,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=6,
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

    def save_key(self, _: Any = None) -> None:
        assert self.key_field is not None
        key = (self.key_field.value or "").strip()
        if not key:
            self.key_field.error = self.tr.t("reports.error.empty_key")
            safe_update(self.key_field)
            return
        self.on_save_key(key)


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
        self.field: ft.TextField | None = None

    def build(self) -> ft.Column:
        self.field = ft.TextField(
            value=self.draft,
            multiline=True,
            min_lines=14,
            capitalization=ft.TextCapitalization.SENTENCES,
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
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
                    content=page_header(
                        self.tr.t("report_review.title"),
                        self.student_name,
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
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
                        ],
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        if self.can_share:
            return bottom_action_bar(
                self.tr.t("report_review.share_pdf"),
                ft.Icons.SHARE,
                self.on_share_pdf,
                secondary=(self.tr.t("report_review.save_pdf"), ft.Icons.DOWNLOAD,
                           self.on_save_pdf),
            )
        return bottom_action_bar(
            self.tr.t("report_review.save_pdf"), ft.Icons.DOWNLOAD, self.on_save_pdf
        )

    def show_error(self, message: str) -> None:
        if self.field is not None:
            self.field.error = message
            safe_update(self.field)
