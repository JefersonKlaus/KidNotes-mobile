"""Reusable UI components shared across screens."""

from typing import Any

import flet as ft

from theme import COLORS


def icon_button(icon: str, tooltip: str, on_click: Any) -> ft.IconButton:
    return ft.IconButton(icon=icon, tooltip=tooltip, on_click=on_click)


def page_header(
    title: str,
    subtitle: str,
    on_back: Any | None = None,
    back_tooltip: str = "",
) -> ft.Row:
    leading = (
        icon_button(ft.Icons.ARROW_BACK, back_tooltip, on_back)
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


def safe_update(control: ft.Control | None) -> None:
    """Update a control if it is on the page (forms are also built in tests, unmounted)."""
    if control is None:
        return
    try:
        control.update()
    except RuntimeError:
        pass


def info_message(text: str, error: bool = False) -> ft.SnackBar:
    """Information message shown at the bottom for a few seconds (e.g. "Event saved")."""
    return ft.SnackBar(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE if error else ft.Icons.INFO_OUTLINE,
                    color=ft.Colors.WHITE,
                ),
                ft.Text(text, color=ft.Colors.WHITE, size=14, expand=True),
            ],
            spacing=10,
        ),
        bgcolor=ft.Colors.ERROR if error else COLORS["primary"],
        behavior=ft.SnackBarBehavior.FLOATING,
        duration=ft.Duration(seconds=4),
        show_close_icon=True,
        close_icon_color=ft.Colors.WHITE,
    )


def empty_state(icon: str, title: str, message: str) -> ft.Container:
    """Card shown when a list has nothing yet."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(icon, color=COLORS["primary"], size=40),
                ft.Text(
                    title,
                    size=16,
                    weight=ft.FontWeight.W_700,
                    color=COLORS["ink"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(message, size=13, color=COLORS["muted"], text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        ),
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=18,
        padding=24,
    )


def _stacked_action(label: str, icon: str, on_click: Any, primary: bool) -> ft.FilledButton:
    """Button with the icon above the label: two of them fit side by side on a phone."""
    foreground = ft.Colors.WHITE if primary else COLORS["primary"]
    return ft.FilledButton(
        content=ft.Column(
            controls=[
                ft.Icon(icon, size=22, color=foreground),
                ft.Text(
                    label,
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE if primary else COLORS["ink"],
                    text_align=ft.TextAlign.CENTER,
                    max_lines=1,
                ),
            ],
            spacing=2,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=on_click,
        height=64,
        expand=True,  # both buttons share the width equally
        style=ft.ButtonStyle(
            bgcolor=COLORS["primary"] if primary else COLORS["lavender"],
            padding=ft.Padding(left=8, right=8, top=6, bottom=6),
            shape=ft.RoundedRectangleBorder(radius=15),
        ),
    )


def bottom_action_bar(
    label: str,
    icon: str,
    on_click: Any,
    secondary: tuple[str, str, Any] | None = None,
) -> ft.Container:
    """Fixed bar at the bottom of a screen with its main action (full width).

    With `secondary` = (label, icon, on_click), the two actions are side by
    side: the secondary one on the left, the main one on the right.
    """
    if secondary is not None:
        return ft.Container(
            content=ft.Row(
                controls=[
                    _stacked_action(*secondary, primary=False),
                    _stacked_action(label, icon, on_click, primary=True),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["surface"],
            border=ft.Border(top=ft.BorderSide(1, COLORS["border"])),
            padding=ft.Padding(left=20, right=20, top=12, bottom=12),
        )
    return ft.Container(
        # `expand` only stretches a button inside a Row/Column, not a Container.
        content=ft.Row(
            controls=[
                ft.FilledButton(
                    label,
                    icon=icon,
                    on_click=on_click,
                    height=54,
                    expand=True,
                    style=ft.ButtonStyle(
                        bgcolor=COLORS["primary"],
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=15),
                    ),
                )
            ],
        ),
        bgcolor=COLORS["surface"],
        border=ft.Border(top=ft.BorderSide(1, COLORS["border"])),
        padding=ft.Padding(left=20, right=20, top=12, bottom=12),
    )


def photo(
    data: bytes | None,
    unavailable_text: str,
    width: float | None = None,
    height: float = 200,
) -> ft.Control:
    """A decrypted photo (bytes in memory), or a placeholder if it can't be read."""
    if data is None:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, color=COLORS["muted"]),
                    ft.Text(unavailable_text, size=12, color=COLORS["muted"]),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            width=width,
            height=height,
            bgcolor=COLORS["background"],
            border_radius=14,
            alignment=ft.Alignment.CENTER,
        )
    return ft.Image(
        src=data,
        width=width,
        height=height,
        fit=ft.BoxFit.COVER,
        border_radius=14,
        # Decode at display size: full-resolution photos use a lot of memory.
        cache_height=int(height * 3),
        gapless_playback=True,
    )
