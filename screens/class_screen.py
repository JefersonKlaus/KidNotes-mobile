"""Class screen: the children of a class.

- Top: "Add student" (mostly used at the beginning of the year).
- List: active children; tap one to open their learning story. The ⋮ menu
  edits or removes (deactivates) the child.
- "Transferred students": removed children stay listed (grey, "Transferred
  on <date>") with a "Reactivate" button.
- Bottom action bar: "Add event" (photos, comments and the children involved).
"""

import logging
from typing import Any

import flet as ft

from components import avatar, bottom_action_bar, empty_state, page_header, safe_update
from dates import to_local_date
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)


class ClassScreen:
    def __init__(
        self,
        class_data: dict[str, Any],
        students: list[dict[str, Any]],
        inactive_students: list[dict[str, Any]],
        event_counts: dict[str, int],
        on_back: Any,
        on_open_child: Any,
        on_add_student: Any,
        on_edit_student: Any,
        on_remove_student: Any,
        on_reactivate_student: Any,
        on_add_event: Any,
        tr: Translator,
        on_open_reports: Any = None,
    ) -> None:
        self.tr = tr
        self.class_data = class_data
        self.students = students
        self.inactive_students = inactive_students
        self.event_counts = event_counts
        self.on_back = on_back
        self.on_open_child = on_open_child
        self.on_add_student = on_add_student
        self.on_edit_student = on_edit_student
        self.on_remove_student = on_remove_student
        self.on_reactivate_student = on_reactivate_student
        self.on_add_event = on_add_event
        self.on_open_reports = on_open_reports

    def build(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=page_header(
                                    self.class_data["name"],
                                    self.tr.plural("students.count", len(self.students)),
                                    on_back=lambda _: self.on_back(),
                                    back_tooltip=self.tr.t("common.back"),
                                ),
                                expand=True,
                            ),
                            ft.OutlinedIconButton(
                                icon=ft.Icons.DESCRIPTION_OUTLINED,
                                tooltip=self.tr.t("reports.open_reports"),
                                on_click=lambda _: self.on_open_reports(),
                                visible=self.on_open_reports is not None,
                            ),
                            # Icon only (rarely used: beginning of the year); the
                            # tooltip names it (long press / screen readers).
                            ft.OutlinedIconButton(
                                icon=ft.Icons.PERSON_ADD_ALT_1,
                                tooltip=self.tr.t("students.add"),
                                on_click=lambda _: self.on_add_student(),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            *(
                                [self._hint(), *[self._student_card(s) for s in self.students]]
                                if self.students
                                else [
                                    empty_state(
                                        ft.Icons.CHILD_CARE,
                                        self.tr.t("students.empty_title"),
                                        self.tr.t("students.empty_message"),
                                    )
                                ]
                            ),
                            *self._transferred_group(),
                        ],
                        spacing=12,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control | None:
        if not self.students:  # an event needs at least one child
            return None
        return bottom_action_bar(
            self.tr.t("students.add_event"),
            ft.Icons.ADD_A_PHOTO,
            lambda _: self.on_add_event(),
        )

    def _hint(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.AUTO_STORIES, color=COLORS["primary"]),
                    ft.Text(self.tr.t("students.hint"), size=13, color=COLORS["ink"], expand=True),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["lavender"],
            border_radius=14,
            padding=14,
        )

    def _birth_text(self, student: dict[str, Any]) -> str:
        birth_date = student.get("birth_date")
        if not birth_date:
            return self.tr.t("students.no_birth_date")
        return self.tr.t(
            "students.birth_info",
            age=self.tr.format_age(birth_date),
            date=self.tr.format_date(birth_date),
        )

    def _events_text(self, student: dict[str, Any]) -> str:
        count = self.event_counts.get(student["id"], 0)
        if count == 0:
            return self.tr.t("students.no_events")
        return self.tr.plural("students.events_count", count)

    def _transferred_group(self) -> list[ft.Control]:
        """Removed students: kept on the screen, grey, so they can be reactivated."""
        if not self.inactive_students:
            return []
        return [
            _transferred_header(
                self.tr.t("students.transferred_group", count=len(self.inactive_students))
            ),
            *[self._transferred_card(s) for s in self.inactive_students],
        ]

    def _transferred_card(self, student: dict[str, Any]) -> ft.Container:
        left_on = to_local_date(student.get("deactivated_at"))
        subtitle = self.tr.t(
            "students.transferred_on", date=self.tr.format_date(left_on) if left_on else "—"
        )
        return ft.Container(
            content=ft.Row(
                controls=[
                    avatar(student["initials"], COLORS["disabled"]),
                    ft.Column(
                        controls=[
                            ft.Text(
                                student["name"],
                                size=16,
                                weight=ft.FontWeight.W_700,
                                color=COLORS["disabled_text"],
                            ),
                            ft.Text(subtitle, size=12, color=COLORS["disabled_text"]),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.OutlinedButton(
                        self.tr.t("students.reactivate"),
                        icon=ft.Icons.RESTORE,
                        on_click=lambda _: self.on_reactivate_student(student),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["inactive_surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=12,
        )

    def _student_card(self, student: dict[str, Any]) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    avatar(student["initials"], student["color"]),
                    ft.Column(
                        controls=[
                            ft.Text(
                                student["name"],
                                size=16,
                                weight=ft.FontWeight.W_700,
                                color=COLORS["ink"],
                            ),
                            ft.Text(self._birth_text(student), size=12, color=COLORS["muted"]),
                            ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.AUTO_STORIES, size=14, color=COLORS["primary"]
                                    ),
                                    ft.Text(
                                        self._events_text(student),
                                        size=12,
                                        color=COLORS["primary"],
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT,
                        tooltip=self.tr.t("students.more_options"),
                        items=[
                            ft.PopupMenuItem(
                                content=self.tr.t("students.edit"),
                                icon=ft.Icons.EDIT_OUTLINED,
                                on_click=lambda _: self.on_edit_student(student),
                            ),
                            ft.PopupMenuItem(
                                content=self.tr.t("students.remove"),
                                icon=ft.Icons.PERSON_REMOVE_OUTLINED,
                                on_click=lambda _: self.on_remove_student(student),
                            ),
                        ],
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=ft.Padding(left=12, right=4, top=12, bottom=12),
            on_click=lambda _: self.on_open_child(student),
        )


def _transferred_header(text: str) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.MOVE_UP, size=18, color=COLORS["disabled_text"]),
                ft.Text(text, size=14, weight=ft.FontWeight.W_700, color=COLORS["disabled_text"]),
            ],
            spacing=8,
        ),
        padding=ft.Padding(top=12),
    )


class RemoveStudentDialog:
    """Confirmation before removing (deactivating) a student from the class."""

    def __init__(
        self,
        repository: Any,
        tr: Translator,
        student: dict[str, Any],
        on_removed: Any,
        on_cancel: Any,
    ) -> None:
        self.repository = repository
        self.tr = tr
        self.student = student
        self.on_removed = on_removed
        self.on_cancel = on_cancel
        self.error_text: ft.Text | None = None

    def build(self) -> ft.AlertDialog:
        self.error_text = ft.Text("", color=ft.Colors.ERROR, size=13, visible=False)
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.t("remove_student.title")),
            content=ft.Column(
                controls=[
                    ft.Text(self.tr.t("remove_student.message", name=self.student["name"])),
                    self.error_text,
                ],
                tight=True,
                spacing=8,
            ),
            actions=[
                ft.TextButton(self.tr.t("common.cancel"), on_click=lambda _: self.on_cancel()),
                ft.FilledButton(
                    self.tr.t("remove_student.confirm"),
                    icon=ft.Icons.PERSON_REMOVE_OUTLINED,
                    on_click=self.confirm,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def confirm(self, _: Any = None) -> None:
        try:
            removed = self.repository.deactivate(self.student["id"])
        except Exception:
            logger.exception("Could not remove the student.")
            assert self.error_text is not None
            self.error_text.value = self.tr.t("remove_student.error")
            self.error_text.visible = True
            safe_update(self.error_text)
            return
        self.on_removed(removed)
