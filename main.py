"""Entry point of the RelatórioFácil Infantil app.

Run with: flet run main.py
"""

import logging

import flet as ft

from app import AppRoot
from database import DatabaseKeyError, open_account_store
from devenv import load_dev_env
from i18n import Translator, detect_device_language
from theme import COLORS

logger = logging.getLogger(__name__)


async def main(page: ft.Page) -> None:
    # English by default; Portuguese when the device language is Portuguese.
    language = await detect_device_language(page)
    try:
        accounts = await open_account_store()
    except DatabaseKeyError:
        logger.exception("The local data could not be decrypted.")
        show_database_error(page, Translator(language))
        return
    # Sign in (or create the account) first; then the teacher's own data opens.
    AppRoot(page, accounts, language)


def show_database_error(page: ft.Page, tr: Translator) -> None:
    """Shown when the database exists but its encryption key is missing or wrong."""
    page.bgcolor = COLORS["background"]
    page.controls.clear()
    page.add(
        ft.SafeArea(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.LOCK_OUTLINE, color=COLORS["primary"], size=48),
                        ft.Text(
                            tr.t("startup.db_error_title"),
                            size=20,
                            weight=ft.FontWeight.W_700,
                            color=COLORS["ink"],
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            tr.t("startup.db_error_message"),
                            size=14,
                            color=COLORS["muted"],
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                padding=32,
                alignment=ft.Alignment.CENTER,
            ),
            expand=True,
        )
    )
    page.update()


if __name__ == "__main__":
    load_dev_env()  # development only: variables from .env (see .env.example)
    ft.run(main)
