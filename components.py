"""Componentes visuais compartilhados entre as telas."""

from typing import Any

import flet as ft

from theme import COLORS


def icon_button(icon: str, tooltip: str, on_click: Any) -> ft.IconButton:
    return ft.IconButton(icon=icon, tooltip=tooltip, on_click=on_click)


def page_header(title: str, subtitle: str, on_back: Any | None = None) -> ft.Row:
    leading = (
        icon_button(ft.Icons.ARROW_BACK, "Voltar", on_back)
        if on_back
        else ft.Container(width=48)
    )
    return ft.Row(
        controls=[
            leading,
            ft.Column(
                controls=[
                    ft.Text(title, size=22, weight=ft.FontWeight.W_700, color=COLORS["ink"]),
                    ft.Text(subtitle, size=13, color=COLORS["muted"]),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def avatar(initials: str, color: str, size: int = 48) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            initials,
            size=size * 0.32,
            weight=ft.FontWeight.W_700,
            color=COLORS["ink"],
            text_align=ft.TextAlign.CENTER,
        ),
        width=size,
        height=size,
        bgcolor=color,
        border_radius=size / 2,
        alignment=ft.Alignment.CENTER,
    )


def section_title(title: str, icon: str) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Icon(icon, color=COLORS["primary"], size=20),
            ft.Text(title, size=16, weight=ft.FontWeight.W_700, color=COLORS["ink"]),
        ],
        spacing=8,
    )
