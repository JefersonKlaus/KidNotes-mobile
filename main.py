"""Entry point of the RelatórioFácil Infantil app.

Run with: flet run main.py
"""

import logging
import os

import flet as ft

from app import AppRoot
from database import DatabaseKeyError, open_account_store
from devenv import load_dev_env
from i18n import Translator, detect_device_language
from theme import COLORS

logger = logging.getLogger(__name__)

# The app's own loggers (module names). Flet's loggers stay at WARNING unless
# `flet run -v` sets FLET_LOG_LEVEL.
APP_LOGGERS = ("__main__", "main", "app", "reports", "database", "screens", "media")
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    """Show the app's logs in the terminal (level: KIDNOTES_LOG_LEVEL, default INFO).

    E.g. every Groq call of "Generate reports" logs its URL, model, HTTP
    status and Groq's error message (see reports/ai.py).
    """
    root_level = logging.getLevelName((os.getenv("FLET_LOG_LEVEL") or "WARNING").upper())
    app_level = logging.getLevelName((os.getenv("KIDNOTES_LOG_LEVEL") or "INFO").upper())
    logging.basicConfig(
        level=root_level if isinstance(root_level, int) else logging.WARNING,
        format=LOG_FORMAT,
    )
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(app_level if isinstance(app_level, int) else logging.INFO)


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
    configure_logging()
    ft.run(main)
