"""Tela de checklist e geração mockada de relatório."""

import asyncio
from typing import Any

import flet as ft

from components import avatar, page_header, section_title
from data import CHECKLIST
from theme import COLORS


class AssessmentScreen:
    def __init__(
        self,
        student: dict[str, str],
        on_back: Any,
        on_report_generated: Any,
        report_text: str = "",
    ) -> None:
        self.student = student
        self.on_back = on_back
        self.on_report_generated = on_report_generated
        self.report_text = report_text
        self.report_field: ft.TextField | None = None
        self.generate_button: ft.Button | None = None
        self.is_generating = False

    def build(self) -> ft.Column:
        self.report_field = ft.TextField(
            label="Relatório pedagógico",
            hint_text="O relatório gerado aparecerá aqui e poderá ser editado.",
            value=self.report_text,
            multiline=True,
            min_lines=6,
            max_lines=10,
            text_size=14,
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
            bgcolor=COLORS["surface"],
        )
        self.generate_button = ft.FilledButton(
            "✨ Gerar relatório com IA",
            icon=ft.Icons.AUTO_AWESOME,
            on_click=self.generate_report,
            height=54,
            style=ft.ButtonStyle(
                bgcolor=COLORS["primary"],
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
        )
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        "Avaliação",
                        self.student["name"],
                        on_back=lambda _: self.on_back(),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    avatar(self.student["initials"], self.student["color"], size=58),
                                    ft.Column(
                                        controls=[
                                            ft.Text(
                                                self.student["name"],
                                                size=18,
                                                weight=ft.FontWeight.W_700,
                                                color=COLORS["ink"],
                                            ),
                                            ft.Text(
                                                "Marque os itens observados hoje",
                                                size=13,
                                                color=COLORS["muted"],
                                            ),
                                        ],
                                        spacing=4,
                                        expand=True,
                                    ),
                                ],
                                spacing=14,
                            ),
                            *[
                                self._checklist_category(name, items)
                                for name, items in CHECKLIST.items()
                            ],
                            ft.Divider(height=8, color="transparent"),
                            section_title("Observações extras", ft.Icons.NOTES),
                            ft.TextField(
                                label="Anotações da professora",
                                hint_text="Conte algo importante sobre o dia da criança...",
                                multiline=True,
                                min_lines=3,
                                max_lines=6,
                                border_radius=14,
                                border_color=COLORS["border"],
                                bgcolor=COLORS["surface"],
                            ),
                            self.generate_button,
                            ft.Container(
                                content=self.report_field,
                                visible=bool(self.report_text),
                                padding=ft.Padding(top=4),
                            ),
                        ],
                        spacing=14,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=30),
                ),
            ],
            spacing=0,
        )

    def _checklist_category(self, name: str, items: list[str]) -> ft.Container:
        category_icons = {
            "Socioemocional": ft.Icons.FAVORITE,
            "Linguagem": ft.Icons.CHAT_BUBBLE_OUTLINE,
            "Motricidade": ft.Icons.DIRECTIONS_RUN,
            "Autonomia": ft.Icons.SELF_IMPROVEMENT,
        }
        return ft.Container(
            content=ft.Column(
                controls=[
                    section_title(name, category_icons[name]),
                    *[
                        ft.Checkbox(
                            label=item,
                            value=False,
                            active_color=COLORS["primary"],
                            label_style=ft.TextStyle(size=14, color=COLORS["ink"]),
                        )
                        for item in items
                    ],
                ],
                spacing=4,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=16,
            padding=14,
        )

    async def generate_report(self, _: ft.ControlEvent) -> None:
        if self.is_generating or self.generate_button is None:
            return
        self.is_generating = True
        self.generate_button.disabled = True
        self.generate_button.content = ft.Row(
            controls=[
                ft.ProgressRing(width=18, height=18, stroke_width=2, color=ft.Colors.WHITE),
                ft.Text("Gerando relatório...", color=ft.Colors.WHITE),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        )
        self.generate_button.update()
        await asyncio.sleep(1.5)
        self.report_text = (
            f"{self.student['name']} participou das propostas com interesse e demonstrou "
            "evolução positiva ao longo da rotina. Interagiu de forma acolhedora "
            "com o grupo e comunicou suas ideias com segurança. Nas atividades "
            "motoras, explorou os materiais com curiosidade e empenho. "
            "Seguiremos incentivando sua autonomia por meio de pequenas escolhas "
            "e responsabilidades diárias.\n\n"
            "Sugestão de continuidade: propor momentos de leitura compartilhada "
            "e brincadeiras que estimulem a expressão oral."
        )
        self.is_generating = False
        self.on_report_generated(self.report_text)
