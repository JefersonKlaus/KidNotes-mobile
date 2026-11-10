"""New class form: saves the class in the encrypted database."""

import logging
from typing import Any

import flet as ft

from components import field_border, safe_update
from database import ClassRepository, ClassValidationError
from database.classes import NAME_MAX_LENGTH
from i18n import Translator
from theme import CLASS_COLORS, COLORS

logger = logging.getLogger(__name__)


class NewClassForm:
    def __init__(
        self,
        repository: ClassRepository,
        tr: Translator,
        on_saved: Any,
        on_cancel: Any,
    ) -> None:
        self.repository = repository
        self.tr = tr
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.selected_color = CLASS_COLORS[0]
        self.name_field: ft.TextField | None = None
        self.color_row: ft.Row | None = None

    def build(self) -> ft.AlertDialog:
        self.name_field = ft.TextField(
            label=self.tr.t("class_form.name_label"),
            hint_text=self.tr.t("class_form.name_hint"),
            max_length=NAME_MAX_LENGTH,
            capitalization=ft.TextCapitalization.SENTENCES,
            autofocus=True,
            border=field_border(focused_color=COLORS["primary"]),
            on_change=self._clear_error,
            on_submit=self.save,
        )
        self.color_row = ft.Row(controls=self._color_swatches(), spacing=10, wrap=True)
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.t("class_form.title")),
            content=ft.Column(
                controls=[
                    self.name_field,
                    ft.Text(self.tr.t("class_form.color_label"), size=13, color=COLORS["muted"]),
                    self.color_row,
                ],
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

    def _color_swatches(self) -> list[ft.Control]:
        return [
            ft.Container(
                content=(
                    ft.Icon(ft.Icons.CHECK, color=COLORS["ink"], size=18)
                    if color == self.selected_color
                    else None
                ),
                width=36,
                height=36,
                bgcolor=color,
                border_radius=18,
                border=ft.Border.all(
                    2, COLORS["ink"] if color == self.selected_color else COLORS["border"]
                ),
                alignment=ft.Alignment.CENTER,
                on_click=lambda _, c=color: self.select_color(c),
            )
            for color in CLASS_COLORS
        ]

    def select_color(self, color: str) -> None:
        self.selected_color = color
        if self.color_row is not None:
            self.color_row.controls = self._color_swatches()
            safe_update(self.color_row)

    def _clear_error(self, _: Any = None) -> None:
        if self.name_field is not None and self.name_field.error:
            self.name_field.error = None
            safe_update(self.name_field)

    def save(self, _: Any = None) -> None:
        assert self.name_field is not None
        try:
            saved = self.repository.add(self.name_field.value or "", self.selected_color)
        except ClassValidationError as error:
            self._show_error(self.tr.t(f"class_form.error.{error.code}"))
            return
        except Exception:
            logger.exception("Could not save the class.")
            self._show_error(self.tr.t("class_form.error.save_failed"))
            return
        self.on_saved(saved)

    def _show_error(self, message: str) -> None:
        assert self.name_field is not None
        self.name_field.error = message
        safe_update(self.name_field)
