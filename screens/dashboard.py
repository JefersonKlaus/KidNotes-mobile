"""Tela de dashboard e lista de turmas."""

from typing import Any

import flet as ft

from components import avatar
from theme import COLORS


class DashboardScreen:
    def __init__(
        self,
        teacher: dict[str, str],
        classes: list[dict[str, Any]],
        on_class_selected: Any,
        on_add_class: Any,
    ) -> None:
        self.teacher = teacher
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
                            ft.Text(
                                "Escolha uma turma para começar",
                                size=15,
                                color=COLORS["muted"],
                            ),
                            *[self._class_card(item) for item in self.classes],
                            ft.FilledButton(
                                "Adicionar nova turma",
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
                                    ft.Text("Olá, professora! 👋", size=14, color=COLORS["muted"]),
                                    ft.Text(
                                        "Suas turmas",
                                        size=28,
                                        weight=ft.FontWeight.W_700,
                                        color=COLORS["ink"],
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            avatar(self.teacher["initials"], COLORS["lavender"], size=52),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        f"{self.teacher['name']} • {self.teacher['role']}",
                        size=13,
                        color=COLORS["muted"],
                    ),
                ],
                spacing=6,
            ),
            padding=ft.Padding(left=24, right=24, top=28, bottom=22),
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
                                f"{len(class_data['students'])} crianças • Toque para abrir",
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
