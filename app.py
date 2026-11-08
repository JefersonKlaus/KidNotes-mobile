"""Estado da aplicacao e roteamento entre telas."""

from typing import Any

import flet as ft

from data import APP_DATA
from screens.assessment import AssessmentScreen
from screens.dashboard import DashboardScreen
from screens.students import StudentsScreen
from theme import COLORS


class RelatorioFacilApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.route = "classes"
        self.selected_class: dict[str, Any] | None = None
        self.selected_student: dict[str, str] | None = None
        self.report_text = ""

        page.title = "RelatórioFácil Infantil"
        page.bgcolor = COLORS["background"]
        page.padding = 0
        page.theme = ft.Theme(
            color_scheme_seed=COLORS["primary"],
            font_family="Nunito",
        )
        page.on_route_change = self._on_route_change
        self.render()

    def render(self) -> None:
        content = self._current_screen()
        self.page.controls.clear()
        self.page.add(
            ft.SafeArea(
                content=ft.Column(
                    controls=[content],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=0,
                ),
                expand=True,
            )
        )
        self.page.update()

    def _current_screen(self) -> ft.Control:
        if self.route == "students" and self.selected_class:
            return StudentsScreen(
                self.selected_class,
                on_back=lambda: self.navigate("classes"),
                on_student_selected=self.open_student,
            ).build()
        if self.route == "assessment" and self.selected_student:
            return AssessmentScreen(
                self.selected_student,
                on_back=lambda: self.navigate("students"),
                on_report_generated=self.set_report,
                report_text=self.report_text,
            ).build()
        return DashboardScreen(
            APP_DATA["teacher"],
            APP_DATA["classes"],
            on_class_selected=self.open_class,
            on_add_class=self.show_add_class_dialog,
        ).build()

    def navigate(self, route: str) -> None:
        self.route = route
        self.render()

    def _on_route_change(self, _: ft.RouteChangeEvent) -> None:
        self.render()

    def open_class(self, class_data: dict[str, Any]) -> None:
        self.selected_class = class_data
        self.navigate("students")

    def open_student(self, student: dict[str, str]) -> None:
        self.selected_student = student
        self.report_text = ""
        self.navigate("assessment")

    def set_report(self, report_text: str) -> None:
        self.report_text = report_text
        self.render()

    def show_add_class_dialog(self, _: ft.ControlEvent) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nova turma"),
            content=ft.Text(
                "A criação de turmas será conectada ao armazenamento "
                "em uma próxima etapa."
            ),
            actions=[
                ft.TextButton(
                    "Entendi",
                    on_click=lambda _: self.page.close(dialog),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
