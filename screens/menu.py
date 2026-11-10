"""The side menu (navigation drawer): Home, Classes, Settings and Sign out.

It opens with the ☰ button on the home screen (the principal class), or by
swiping from the left edge of any screen of the signed-in app (it belongs to
the page, not to a screen).
"""

from typing import Any

import flet as ft

from i18n import Translator
from theme import COLORS

APP_NAME = "RelatórioFácil Infantil"


def menu_button(tr: Translator, on_click: Any) -> ft.IconButton:
    """☰ that opens the side menu."""
    return ft.IconButton(icon=ft.Icons.MENU, tooltip=tr.t("menu.open"), on_click=on_click,
                         data="menu")


def build_menu(tr: Translator, email: str, on_home: Any, on_classes: Any, on_settings: Any,
               on_sign_out: Any) -> ft.NavigationDrawer:
    header = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(ft.Icons.AUTO_STORIES, color=COLORS["primary"], size=36),
                ft.Text(APP_NAME, size=18, weight=ft.FontWeight.W_700, color=COLORS["ink"]),
                ft.Text(email, size=13, color=COLORS["muted"]),
            ],
            spacing=4,
        ),
        padding=ft.Padding(left=24, right=24, top=28, bottom=16),
    )
    return ft.NavigationDrawer(
        controls=[
            header,
            ft.Divider(),
            _item(ft.Icons.HOME_OUTLINED, tr.t("menu.home"), on_home, "home"),
            _item(ft.Icons.GROUPS_OUTLINED, tr.t("menu.classes"), on_classes, "classes"),
            _item(ft.Icons.SETTINGS_OUTLINED, tr.t("menu.settings"), on_settings, "settings"),
            ft.Divider(),
            _item(ft.Icons.LOGOUT, tr.t("dashboard.sign_out"), on_sign_out, "sign_out"),
        ],
        selected_index=-1,  # actions, not destinations: nothing highlighted
        bgcolor=COLORS["surface"],
    )


def _item(icon: str, label: str, on_click: Any, name: str) -> ft.ListTile:
    return ft.ListTile(
        leading=ft.Icon(icon, color=COLORS["primary"]),
        title=ft.Text(label, size=15, color=COLORS["ink"]),
        on_click=on_click,
        data=f"menu:{name}",
    )
