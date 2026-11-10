"""Classes page (side menu → Classes): all the teacher's classes.

There is no back button: like home, it has ☰, and the side menu leads to Home.

- Tap a class: manage its students (add, edit, remove, reactivate).
- ★: set it as the principal class, the one the app opens on (home).
- "Add new class".
"""

from typing import Any

import flet as ft

from components import empty_state
from i18n import Translator
from screens.menu import menu_button
from theme import COLORS


class ClassesScreen:
    def __init__(
        self,
        classes: list[dict[str, Any]],
        default_class_id: str | None,
        tr: Translator,
        on_open_menu: Any,
        on_manage_class: Any,
        on_set_default: Any,
        on_add_class: Any,
    ) -> None:
        """`classes`: each with "student_count" (active students)."""
        self.classes = classes
        self.default_class_id = default_class_id
        self.tr = tr
        self.on_open_menu = on_open_menu
        self.on_manage_class = on_manage_class
        self.on_set_default = on_set_default
        self.on_add_class = on_add_class

    def build(self) -> ft.Column:
        cards: list[ft.Control] = (
            [self._class_card(c) for c in self.classes]
            if self.classes
            else [
                empty_state(
                    ft.Icons.GROUPS_OUTLINED,
                    self.tr.t("dashboard.empty_title"),
                    self.tr.t("dashboard.empty_message"),
                )
            ]
        )
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            menu_button(self.tr, self.on_open_menu),
                            ft.Column(
                                controls=[
                                    ft.Text(self.tr.t("dashboard.title"), size=22,
                                            weight=ft.FontWeight.W_700, color=COLORS["ink"]),
                                    ft.Text(self.tr.t("classes.subtitle"), size=13,
                                            color=COLORS["muted"]),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            *cards,
                            ft.FilledButton(
                                self.tr.t("dashboard.add_class"),
                                icon=ft.Icons.ADD,
                                on_click=self.on_add_class,
                                height=52,
                                style=ft.ButtonStyle(
                                    bgcolor=COLORS["primary"],
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=14),
                                ),
                            ),
                        ],
                        spacing=14,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def _class_card(self, class_data: dict[str, Any]) -> ft.Container:
        is_default = class_data["id"] == self.default_class_id
        title: list[ft.Control] = [
            ft.Text(class_data["name"], size=16, weight=ft.FontWeight.W_700,
                    color=COLORS["ink"]),
        ]
        if is_default:
            title.append(
                ft.Container(
                    content=ft.Text(self.tr.t("classes.principal"), size=11,
                                    weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                    bgcolor=COLORS["primary"],
                    border_radius=8,
                    padding=ft.Padding(left=8, right=8, top=2, bottom=2),
                    data="principal",
                )
            )
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(ft.Icons.GROUP, color=COLORS["ink"], size=25),
                        width=52,
                        height=52,
                        bgcolor=class_data["color"],
                        border_radius=16,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Row(controls=title, spacing=8, wrap=True),
                            ft.Text(
                                self.tr.plural("dashboard.students_count",
                                               class_data.get("student_count", 0)),
                                size=13,
                                color=COLORS["muted"],
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.STAR if is_default else ft.Icons.STAR_BORDER,
                        icon_color=COLORS["primary"],
                        tooltip=self.tr.t("classes.is_default" if is_default
                                          else "classes.set_default"),
                        # Already the principal class: nothing to do.
                        on_click=None if is_default
                        else (lambda _, c=class_data: self.on_set_default(c)),
                        data=f"default:{class_data['id']}",
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(2 if is_default else 1,
                                 COLORS["primary"] if is_default else COLORS["border"]),
            border_radius=18,
            padding=ft.Padding(left=14, right=6, top=14, bottom=14),
            on_click=lambda _: self.on_manage_class(class_data),
            data=f"class:{class_data['id']}",
        )
