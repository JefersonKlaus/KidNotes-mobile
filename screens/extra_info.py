"""Extra information screen: free notes about the child (no date).

A full screen (not a dialog) because teachers use it as a notebook about the
child: likes, habits, what helps them... The text being written is kept by the
app controller (`draft`) until it is saved or discarded.
"""

import logging
from typing import Any

import flet as ft

from components import bottom_action_bar, field_border, page_header, safe_update
from database import StudentValidationError
from database.students import NOTES_MAX_LENGTH
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)


class ExtraInfoScreen:
    def __init__(
        self,
        student: dict[str, Any],
        draft: str,
        repository: Any,
        tr: Translator,
        on_change: Any,
        on_saved: Any,
        on_back: Any,
    ) -> None:
        self.student = student
        self.draft = draft
        self.repository = repository
        self.tr = tr
        self.on_change = on_change
        self.on_saved = on_saved
        self.on_back = on_back
        self.field: ft.TextField | None = None

    def build(self) -> ft.Column:
        self.field = ft.TextField(
            value=self.draft,
            hint_text=self.tr.t("child.extra_info_placeholder"),
            multiline=True,
            min_lines=12,  # a big writing area; it grows with the text
            max_length=NOTES_MAX_LENGTH,
            capitalization=ft.TextCapitalization.SENTENCES,
            autofocus=not self.draft,
            border=field_border(focused_color=COLORS["primary"]),
            bgcolor=COLORS["surface"],
            text_size=15,
            on_change=self._on_change,
        )
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.tr.t("child.extra_info"),
                        self.student["name"],
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.NOTE_ALT_OUTLINED,
                                        color=COLORS["primary"],
                                        size=20,
                                    ),
                                    ft.Text(
                                        self.tr.t(
                                            "child.extra_info_hint", name=self.student["name"]
                                        ),
                                        size=13,
                                        color=COLORS["muted"],
                                        expand=True,
                                    ),
                                ],
                                spacing=10,
                            ),
                            self.field,
                        ],
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,  # full width
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        return bottom_action_bar(self.tr.t("common.save"), ft.Icons.CHECK, self.save)

    def _on_change(self, event: Any) -> None:
        self.on_change(event.control.value or "")
        if self.field is not None and self.field.error:
            self.field.error = None
            safe_update(self.field)

    def save(self, _: Any = None) -> None:
        assert self.field is not None
        try:
            saved = self.repository.update_notes(self.student["id"], self.field.value or "")
        except StudentValidationError as error:
            self._show_error(self.tr.t(f"child.error.{error.code}"))
            return
        except Exception:
            logger.exception("Could not save the extra information.")
            self._show_error(self.tr.t("child.error.save_failed"))
            return
        self.on_saved(saved)

    def _show_error(self, message: str) -> None:
        assert self.field is not None
        self.field.error = message
        safe_update(self.field)
