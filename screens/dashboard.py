"""Dashboard screen: the signed-in teacher and their class list."""

from typing import Any

import flet as ft

from i18n import Translator
from theme import COLORS


class DashboardScreen:
    def __init__(
        self,
        account_email: str,
        classes: list[dict[str, Any]],
        on_class_selected: Any,
        on_add_class: Any,
        tr: Translator,
        on_sign_out: Any = None,
    ) -> None:
        self.tr = tr
        self.account_email = account_email
        self.on_sign_out = on_sign_out
        self.classes = classes
        self.on_class_selected = on_class_selected
        self.on_add_class = on_add_class

    def build(self) -> ft.Column:
        return ft.Column(
            controls=[
                self._welcome_header(),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            *(
                                [
                                    ft.Text(
                                        self.tr.t("dashboard.choose_class"),
                                        size=15,
                                        color=COLORS["muted"],
                                    ),
                                    *[self._class_card(item) for item in self.classes],
                                ]
                                if self.classes
                                else [self._empty_state()]
                            ),
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
                    padding=ft.Padding(left=20, right=20, bottom=24),
                ),
            ],
            spacing=0,
        )

    def _welcome_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        self.tr.t("dashboard.greeting"),
                                        size=14,
                                        color=COLORS["muted"],
                                    ),
                                    ft.Text(
                                        self.tr.t("dashboard.title"),
                                        size=28,
                                        weight=ft.FontWeight.W_700,
                                        color=COLORS["ink"],
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                self.account_email,
                                size=13,
                                color=COLORS["muted"],
                                expand=True,
                            ),
                            ft.TextButton(
                                self.tr.t("dashboard.sign_out"),
                                icon=ft.Icons.LOGOUT,
                                on_click=lambda _: self.on_sign_out(),
                                visible=self.on_sign_out is not None,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=6,
            ),
            padding=ft.Padding(left=24, right=24, top=28, bottom=22),
        )

    def _empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.GROUPS_OUTLINED, color=COLORS["primary"], size=40),
                    ft.Text(
                        self.tr.t("dashboard.empty_title"),
                        size=16,
                        weight=ft.FontWeight.W_700,
                        color=COLORS["ink"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        self.tr.t("dashboard.empty_message"),
                        size=13,
                        color=COLORS["muted"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=24,
        )

    def _class_card(self, class_data: dict[str, Any]) -> ft.Container:
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
                            ft.Text(
                                class_data["name"],
                                size=16,
                                weight=ft.FontWeight.W_700,
                                color=COLORS["ink"],
                            ),
                            ft.Text(
                                self.tr.plural(
                                    "dashboard.students_count", class_data.get("student_count", 0)
                                ),
                                size=13,
                                color=COLORS["muted"],
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=COLORS["muted"]),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=14,
            on_click=lambda _: self.on_class_selected(class_data),
        )
