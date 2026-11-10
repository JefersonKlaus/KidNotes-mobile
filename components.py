"""Reusable UI components shared across screens."""

import asyncio
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


FIELD_RADIUS = 14


def field_border(focused_color: str | None = None) -> Any:
    """Rounded outline of the app's text fields.

    Flet 1.0 deprecated `TextField(border_radius=, border_color=,
    focused_border_color=)` (removed in 1.3) and warns (DeprecationWarning)
    when such a field is put on the page. `border=` is the replacement.
    Without `focused_color`, the focused outline keeps the theme's color.
    """
    normal = ft.OutlineInputBorder(
        border_radius=FIELD_RADIUS, side=ft.BorderSide(1, COLORS["border"])
    )
    if focused_color is None:
        return normal
    return {
        ft.ControlState.DEFAULT: normal,
        ft.ControlState.FOCUSED: ft.OutlineInputBorder(
            border_radius=FIELD_RADIUS, side=ft.BorderSide(2, focused_color)
        ),
    }


def safe_update(control: ft.Control | None) -> None:
    """Update a control if it is on the page (forms are also built in tests, unmounted)."""
    if control is None:
        return
    try:
        control.update()
    except RuntimeError:
        pass


NOTICE_SECONDS = 4


class TopNotice:
    """Information message at the TOP of the screen (e.g. "Report deleted.").

    It floats over the page (`page.overlay`), so the buttons of the bottom
    action bars stay visible and the page doesn't move. It hides itself after
    NOTICE_SECONDS (or with its ✕); a new message replaces the previous one.
    """

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.control: ft.Container | None = None
        self._count = 0  # which message is on screen (for the delayed hide)

    def show(self, text: str, error: bool = False) -> None:
        self._remove()
        self._count += 1
        self.control = self._build(text, error)
        self.page.overlay.append(self.control)
        self.page.update()
        self.page.run_task(self._hide_later, self._count)

    def hide(self) -> None:
        if self._remove():
            self.page.update()

    async def _hide_later(self, count: int) -> None:
        await asyncio.sleep(NOTICE_SECONDS)
        if count == self._count:  # not replaced by a newer message meanwhile
            self.hide()

    def _remove(self) -> bool:
        control, self.control = self.control, None
        if control is not None and control in self.page.overlay:
            self.page.overlay.remove(control)
            return True
        return False

    def _build(self, text: str, error: bool) -> ft.Container:
        card = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE if error else ft.Icons.INFO_OUTLINE,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Text(text, color=ft.Colors.WHITE, size=14, expand=True),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_color=ft.Colors.WHITE,
                        icon_size=18,
                        on_click=lambda _: self.hide(),
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.ERROR if error else COLORS["primary"],
            border_radius=14,
            padding=ft.Padding(left=16, right=4, top=4, bottom=4),
            margin=12,
            shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.25, "#000000")),
        )
        # Pinned to the top edge, full width; SafeArea keeps it below the status bar.
        return ft.Container(
            content=ft.SafeArea(content=card),
            top=0,
            left=0,
            right=0,
            data="notice",
        )


def empty_state(icon: str, title: str, message: str) -> ft.Row:
    """Card shown when a list has nothing yet, as wide as the list.

    A Container takes the width of its content (here, centered text), so the
    card is put in a Row with `expand`: it fills the whole width.
    """
    card = ft.Container(
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
        expand=True,
    )
    return ft.Row(controls=[card])


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
