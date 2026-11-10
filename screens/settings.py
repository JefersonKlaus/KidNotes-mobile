"""Settings: the account and the Groq API key used by the AI reports.

Opened from the side menu (screens/menu.py) or from the report screen when no
key is configured. The key is stored encrypted in the teacher's account.
"""

from typing import Any

import flet as ft

from components import field_border, page_header, safe_update, section_title
from i18n import Translator
from theme import COLORS


class SettingsScreen:
    def __init__(
        self,
        email: str,
        has_saved_key: bool,
        env_key_in_use: bool,
        editing_key: bool,
        tr: Translator,
        on_back: Any,
        on_save_key: Any,
        on_change_key: Any,
        on_remove_key: Any,
    ) -> None:
        """`env_key_in_use`: no saved key, but GROQ_API_KEY is set (development)."""
        self.email = email
        self.has_saved_key = has_saved_key
        self.env_key_in_use = env_key_in_use
        self.editing_key = editing_key
        self.tr = tr
        self.on_back = on_back
        self.on_save_key = on_save_key
        self.on_change_key = on_change_key
        self.on_remove_key = on_remove_key
        self.key_field: ft.TextField | None = None

    def build(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.tr.t("settings.title"),
                        self.email,
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            section_title(self.tr.t("settings.account"),
                                          ft.Icons.ACCOUNT_CIRCLE_OUTLINED),
                            ft.Text(self.email, size=14, color=COLORS["ink"]),
                            section_title(self.tr.t("settings.ai_title"), ft.Icons.AUTO_AWESOME),
                            self._api_key_section(),
                        ],
                        spacing=14,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def _api_key_section(self) -> ft.Control:
        if self.has_saved_key and not self.editing_key:
            return ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY, size=18, color=COLORS["primary"]),
                    ft.Text(self.tr.t("settings.api_key_configured"), size=13,
                            color=COLORS["muted"], expand=True),
                    ft.TextButton(self.tr.t("settings.api_key_change"),
                                  on_click=lambda _: self.on_change_key()),
                    ft.TextButton(self.tr.t("settings.api_key_remove"),
                                  on_click=lambda _: self.on_remove_key(),
                                  style=ft.ButtonStyle(color=ft.Colors.ERROR)),
                ],
                spacing=4,
            )
        self.key_field = ft.TextField(
            label=self.tr.t("settings.api_key"),
            password=True,
            can_reveal_password=True,
            autocorrect=False,
            enable_suggestions=False,
            helper=self.tr.t("settings.api_key_help"),
            border=field_border(),
            bgcolor=COLORS["surface"],
            on_submit=self.save_key,
        )
        controls: list[ft.Control] = []
        if self.env_key_in_use:
            controls.append(ft.Text(self.tr.t("settings.api_key_env"), size=12,
                                    color=COLORS["muted"]))
        controls += [
            self.key_field,
            ft.Row(
                controls=[
                    ft.OutlinedButton(self.tr.t("settings.api_key_save"), icon=ft.Icons.KEY,
                                      on_click=self.save_key)
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]
        return ft.Column(controls=controls, spacing=6)

    def save_key(self, _: Any = None) -> None:
        assert self.key_field is not None
        key = (self.key_field.value or "").strip()
        if not key:
            self.key_field.error = self.tr.t("settings.error.empty_key")
            safe_update(self.key_field)
            return
        self.on_save_key(key)
