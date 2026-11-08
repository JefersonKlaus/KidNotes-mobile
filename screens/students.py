"""Tela de alunos de uma turma."""

from typing import Any

import flet as ft

from components import avatar, page_header
from theme import COLORS


class StudentsScreen:
    def __init__(
        self,
        class_data: dict[str, Any],
        on_back: Any,
        on_student_selected: Any,
    ) -> None:
        self.class_data = class_data
        self.on_back = on_back
        self.on_student_selected = on_student_selected

    def build(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.class_data["name"],
                        "Lista de alunos",
                        on_back=lambda _: self.on_back(),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.INFO_OUTLINE, color=COLORS["primary"]),
                                        ft.Text(
                                            "Selecione uma criança para iniciar a avaliação.",
                                            size=13,
                                            color=COLORS["ink"],
                                            expand=True,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                bgcolor=COLORS["lavender"],
                                border_radius=14,
                                padding=14,
                            ),
                            *[self._student_card(student) for student in self.class_data["students"]],
                        ],
                        spacing=12,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def _student_card(self, student: dict[str, str]) -> ft.Container:
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
                            ft.Text(
                                "Avaliação ainda não iniciada",
                                size=12,
                                color=COLORS["muted"],
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.FilledButton(
                        "Avaliar",
                        icon=ft.Icons.EDIT_NOTE,
                        on_click=lambda _: self.on_student_selected(student),
                        height=44,
                        style=ft.ButtonStyle(
                            bgcolor=COLORS["mint"],
                            color=COLORS["ink"],
                            shape=ft.RoundedRectangleBorder(radius=12),
                        ),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=12,
        )
