"""Student form (add / edit): name and birth date, saved in the encrypted database."""

import logging
from datetime import date
from typing import Any

import flet as ft

from components import safe_update
from database import StudentRepository, StudentValidationError
from database.students import MIN_BIRTH_DATE, NAME_MAX_LENGTH
from dates import to_local_date
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)


class StudentForm:
    """Adds a student to `class_id`, or edits `student` when it is given."""

    def __init__(
        self,
        repository: StudentRepository,
        tr: Translator,
        page: ft.Page,
        class_id: str,
        on_saved: Any,
        on_cancel: Any,
        student: dict[str, Any] | None = None,
    ) -> None:
        self.repository = repository
        self.tr = tr
        self.page = page
        self.class_id = class_id
        self.student = student
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.birth_date: date | None = student["birth_date"] if student else None
        self.name_field: ft.TextField | None = None
        self.birth_field: ft.TextField | None = None
        self.date_picker: ft.DatePicker | None = None

    @property
    def is_edit(self) -> bool:
        return self.student is not None

    def build(self) -> ft.AlertDialog:
        self.name_field = ft.TextField(
            label=self.tr.t("student_form.name_label"),
            value=self.student["name"] if self.student else "",
            max_length=NAME_MAX_LENGTH,
            capitalization=ft.TextCapitalization.WORDS,
            autofocus=not self.is_edit,
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
            on_change=lambda _: self._clear_error(self.name_field),
            on_submit=self.save,
        )
        self.birth_field = ft.TextField(
            label=self.tr.t("student_form.birth_label"),
            hint_text=self.tr.t("student_form.birth_hint"),
            read_only=True,
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
            prefix_icon=ft.Icons.CAKE_OUTLINED,
            on_click=self.open_date_picker,
        )
        self._refresh_birth_field()
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(
                self.tr.t("student_form.edit_title" if self.is_edit else "student_form.add_title")
            ),
            content=ft.Column(
                controls=[self.name_field, self.birth_field],
                tight=True,
                spacing=12,
                width=360,
            ),
            actions=[
                ft.TextButton(self.tr.t("common.cancel"), on_click=lambda _: self.on_cancel()),
                ft.FilledButton(
                    self.tr.t("common.save"),
                    on_click=self.save,
                    style=ft.ButtonStyle(bgcolor=COLORS["primary"], color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # --- birth date ------------------------------------------------------------

    def open_date_picker(self, _: Any = None) -> None:
        today = date.today()
        self.date_picker = ft.DatePicker(
            value=self.birth_date or date(today.year - 3, today.month, 1),
            first_date=MIN_BIRTH_DATE,
            last_date=today,
            entry_mode=ft.DatePickerEntryMode.CALENDAR,
            help_text=self.tr.t("student_form.birth_label"),
            on_change=self._on_date_picked,
        )
        self.page.show_dialog(self.date_picker)

    def _on_date_picked(self, event: Any) -> None:
        value = getattr(event, "data", None)
        if value is None and self.date_picker is not None:
            value = self.date_picker.value
        self.set_birth_date(to_local_date(value))

    def set_birth_date(self, value: date | None) -> None:
        self.birth_date = value
        self._refresh_birth_field()
        self._clear_error(self.birth_field)
        safe_update(self.birth_field)

    def _refresh_birth_field(self) -> None:
        assert self.birth_field is not None
        self.birth_field.value = self.tr.format_date(self.birth_date) if self.birth_date else ""
        self.birth_field.suffix_icon = (
            ft.IconButton(
                icon=ft.Icons.CLOSE,
                tooltip=self.tr.t("student_form.clear_date"),
                on_click=lambda _: self.set_birth_date(None),
            )
            if self.birth_date
            else ft.IconButton(
                icon=ft.Icons.CALENDAR_MONTH,
                tooltip=self.tr.t("student_form.pick_date"),
                on_click=self.open_date_picker,
            )
        )

    # --- save --------------------------------------------------------------------

    def save(self, _: Any = None) -> None:
        assert self.name_field is not None
        name = self.name_field.value or ""
        try:
            if self.student:
                saved = self.repository.update(self.student["id"], name, self.birth_date)
            else:
                saved = self.repository.add(self.class_id, name, self.birth_date)
        except StudentValidationError as error:
            field = self.name_field if error.code.startswith("name") else self.birth_field
            self._show_error(field, self.tr.t(f"student_form.error.{error.code}"))
            return
        except Exception:
            logger.exception("Could not save the student.")
            self._show_error(self.name_field, self.tr.t("student_form.error.save_failed"))
            return
        self.on_saved(saved)

    def _show_error(self, field: ft.TextField | None, message: str) -> None:
        if field is not None:
            field.error = message
            safe_update(field)

    @staticmethod
    def _clear_error(field: ft.TextField | None) -> None:
        if field is not None and field.error:
            field.error = None
            safe_update(field)
