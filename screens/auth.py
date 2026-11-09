"""Sign-in / registration screen (local account: email + password).

The password protects the teacher's encrypted data on this device (see
database/accounts.py): it can't be recovered, so the registration screen warns
about it.
"""

import logging
from typing import Any

import flet as ft

from components import safe_update
from database import AccountError, AccountStore
from database.accounts import PASSWORD_MIN_LENGTH
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)

LOGIN = "login"
REGISTER = "register"


class AuthScreen:
    def __init__(
        self,
        accounts: AccountStore,
        tr: Translator,
        on_authenticated: Any,
        on_switch_mode: Any,
        mode: str | None = None,
    ) -> None:
        self.accounts = accounts
        self.tr = tr
        self.on_authenticated = on_authenticated
        self.on_switch_mode = on_switch_mode
        # First use of the app on this device: create the account.
        self.mode = mode or (LOGIN if accounts.has_accounts() else REGISTER)
        self.email: ft.TextField | None = None
        self.password: ft.TextField | None = None
        self.confirmation: ft.TextField | None = None
        self.error_text: ft.Text | None = None

    @property
    def registering(self) -> bool:
        return self.mode == REGISTER

    def _field(self, label: str, **kwargs: Any) -> ft.TextField:
        return ft.TextField(
            label=self.tr.t(label),
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
            bgcolor=COLORS["surface"],
            autocorrect=False,
            enable_suggestions=False,
            on_submit=self.submit,
            **kwargs,
        )

    def build(self) -> ft.Control:
        # Signing in again: the email of the last account used on this device
        # is already filled in, so the teacher only types the password.
        known_email = None if self.registering else self.accounts.last_email()
        self.email = self._field(
            "auth.email",
            value=known_email or "",
            keyboard_type=ft.KeyboardType.EMAIL,
            autofill_hints=[ft.AutofillHint.EMAIL],
            autofocus=not known_email,
        )
        password_hint = (
            ft.AutofillHint.NEW_PASSWORD if self.registering else ft.AutofillHint.PASSWORD
        )
        self.password = self._field(
            "auth.password",
            password=True,
            can_reveal_password=True,
            autofill_hints=[password_hint],
            autofocus=bool(known_email),
            helper=(
                self.tr.t("auth.password_hint", count=PASSWORD_MIN_LENGTH)
                if self.registering
                else None
            ),
        )
        self.confirmation = (
            self._field(
                "auth.confirm_password",
                password=True,
                can_reveal_password=True,
                autofill_hints=[ft.AutofillHint.NEW_PASSWORD],
            )
            if self.registering
            else None
        )
        self.error_text = ft.Text("", color=ft.Colors.ERROR, size=13, visible=False)
        notice = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOCK_OUTLINE, color=COLORS["primary"], size=20),
                    ft.Text(
                        self.tr.t("auth.register_notice"), size=12, color=COLORS["ink"], expand=True
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLORS["lavender"],
            border_radius=14,
            padding=12,
            visible=self.registering,
        )
        card = ft.Column(
            controls=[
                ft.Icon(ft.Icons.AUTO_STORIES, color=COLORS["primary"], size=48),
                ft.Text(
                    "RelatórioFácil Infantil",
                    size=24,
                    weight=ft.FontWeight.W_700,
                    color=COLORS["ink"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    self.tr.t(
                        "auth.register_subtitle" if self.registering else "auth.login_subtitle"
                    ),
                    size=14,
                    color=COLORS["muted"],
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                self.email,
                self.password,
                *([self.confirmation] if self.confirmation else []),
                notice,
                self.error_text,
                ft.Row(
                    controls=[
                        ft.FilledButton(
                            self.tr.t(
                                "auth.create_account" if self.registering else "auth.sign_in"
                            ),
                            icon=ft.Icons.PERSON_ADD_ALT_1 if self.registering else ft.Icons.LOGIN,
                            on_click=self.submit,
                            height=52,
                            expand=True,
                            style=ft.ButtonStyle(
                                bgcolor=COLORS["primary"],
                                color=ft.Colors.WHITE,
                                shape=ft.RoundedRectangleBorder(radius=14),
                            ),
                        )
                    ]
                ),
                ft.TextButton(
                    self.tr.t("auth.go_to_login" if self.registering else "auth.go_to_register"),
                    on_click=lambda _: self.on_switch_mode(LOGIN if self.registering else REGISTER),
                ),
            ],
            spacing=14,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        return ft.Container(
            content=ft.Row(
                controls=[ft.Container(content=card, width=440)],  # readable on tablets
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=24, right=24, top=48, bottom=24),
        )

    def submit(self, _: Any = None) -> None:
        assert self.email is not None and self.password is not None
        try:
            if self.registering:
                assert self.confirmation is not None
                session = self.accounts.register(
                    self.email.value or "", self.password.value or "", self.confirmation.value or ""
                )
            else:
                session = self.accounts.login(self.email.value or "", self.password.value or "")
        except AccountError as error:
            self._show_error(self.tr.t(f"auth.error.{error.code}"))
            return
        except Exception:
            logger.exception("Sign-in / registration failed.")
            self._show_error(self.tr.t("auth.error.failed"))
            return
        self.on_authenticated(session)

    def _show_error(self, message: str) -> None:
        assert self.error_text is not None
        self.error_text.value = message
        self.error_text.visible = True
        safe_update(self.error_text)
