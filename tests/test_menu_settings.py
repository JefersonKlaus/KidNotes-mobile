"""Side menu (Settings, Sign out), the Settings screen (Groq API key) and the
saved reports grouped by month on the report screen."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import flet as ft
import pytest

from i18n import Translator
from tests.conftest import (
    collect_texts,
    find_all,
    find_button,
    notice_text,
    open_menu,
    screen_text,
    side_menu_item,
    sign_out_from_menu,
    sign_up,
)
from tests.test_app import by_name, layout, start, start_root
from tests.test_reports import open_reports

# --- side menu ---------------------------------------------------------------------------


def test_menu_opens_settings_and_back_goes_home(make_page, repositories):
    page = make_page()
    app = start(page, repositories, "en")

    open_menu(page)
    asyncio.run(side_menu_item(page, "settings").on_click(None))

    assert not page.drawer_open  # the menu closes
    assert app.route == "settings" and "Settings" in screen_text(page)
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)
    assert app.route == "class"  # home


def test_the_menu_stays_available_on_other_screens(make_page, repositories, sample_class):
    """It belongs to the page: a swipe from the left edge opens it anywhere."""
    page = make_page()
    app = start(page, repositories, "en")
    menu = page.drawer
    app.manage_class(sample_class)  # a screen without ☰
    assert page.drawer is menu
    asyncio.run(page.show_drawer())  # swipe from the left edge
    asyncio.run(side_menu_item(page, "settings").on_click(None))
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)
    assert app.route == "manage_class"  # back to where Settings was opened


def test_menu_has_home_and_classes(make_page, repositories, sample_class):
    page = make_page()
    app = start(page, repositories, "en")
    texts = collect_texts(open_menu(page))
    assert [t for t in texts if t in ("Home", "Classes", "Settings", "Sign out")] == [
        "Home", "Classes", "Settings", "Sign out"]

    asyncio.run(side_menu_item(page, "classes").on_click(None))
    assert app.route == "classes" and "Your classes" in screen_text(page)
    assert not page.drawer_open

    open_menu(page)
    asyncio.run(side_menu_item(page, "home").on_click(None))
    assert app.route == "class" and sample_class["name"] in screen_text(page)


def test_sign_out_from_the_menu(make_page):
    page = make_page()
    root = start_root(page)
    sign_up(page)

    sign_out_from_menu(page)

    assert root.session is None and page.drawer is None
    assert "Sign in to open your classes." in screen_text(page)


def test_menu_in_portuguese_and_language_change(make_page, repositories):
    page = make_page()
    app = start(page, repositories, "pt")
    texts = collect_texts(open_menu(page))
    assert {"Início", "Turmas", "Configurações", "Sair"} <= set(texts)

    app._on_locale_change(type("E", (), {"locales": [ft.Locale("en", "US")]})())
    texts = collect_texts(page.drawer)
    assert "Settings" in texts and "Sign out" in texts


# --- settings: the Groq API key -----------------------------------------------------------


def open_settings(page, repositories, monkeypatch, key=None, env_key=None):
    if env_key:
        monkeypatch.setenv("GROQ_API_KEY", env_key)
    else:
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
    if key:
        repositories.settings.set_groq_api_key(key)
    app = start(page, repositories, "en")
    app.open_settings()
    return app


def key_field(page):
    fields = [f for f in find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
              if f.label == "Groq API key"]
    return fields[0] if fields else None


def test_settings_shows_the_account(make_page, repositories, monkeypatch):
    page = make_page()
    app = open_settings(page, repositories, monkeypatch)
    app.account_email = "ana@school.org"
    app.render()
    text = screen_text(page)
    assert "Account" in text and "ana@school.org" in text and "AI reports (Groq)" in text


def test_save_change_and_remove_the_key(make_page, repositories, monkeypatch, database):
    page = make_page()
    app = open_settings(page, repositories, monkeypatch)
    field = key_field(page)
    assert field.password and field.can_reveal_password

    find_button(page.controls[-1], "Save key").on_click(None)
    assert field.error == "Paste the API key."
    field.value = "  gsk_new  "
    find_button(page.controls[-1], "Save key").on_click(None)

    assert repositories.settings.get_groq_api_key() == "gsk_new"
    assert "Groq API key configured" in screen_text(page) and key_field(page) is None
    assert notice_text(page) == "API key saved."

    find_button(page.controls[-1], "Change").on_click(None)
    assert key_field(page) is not None

    app.open_settings()  # opening Settings again: the key is shown as configured
    assert key_field(page) is None
    find_button(page.controls[-1], "Remove").on_click(None)

    assert repositories.settings.get_groq_api_key() is None
    assert database.get("settings", "groq_api_key") is None  # deleted, not just emptied
    assert key_field(page) is not None and notice_text(page) == "API key removed."


def test_development_key_from_the_environment(make_page, repositories, monkeypatch):
    page = make_page()
    open_settings(page, repositories, monkeypatch, env_key="gsk_env")
    assert "Using GROQ_API_KEY from the environment (development)." in screen_text(page)
    assert key_field(page) is not None  # a key can still be saved to replace it


def test_settings_in_portuguese(make_page, repositories, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    page = make_page()
    app = start(page, repositories, "pt")
    app.open_settings()
    text = screen_text(page)
    assert "Configurações" in text and "Relatórios com IA (Groq)" in text
    assert key_field(page) is None  # pt label
    assert any(f.label == "Chave da API Groq" for f in find_all(
        page.controls[-1], lambda c: isinstance(c, ft.TextField)))


# --- saved reports grouped by month --------------------------------------------------------


def report_made_on(repositories, database, sample_class, name, made):
    student = by_name(repositories, sample_class["id"], name)
    report = repositories.reports.add(sample_class["id"], student["id"], made - timedelta(30),
                                      made, f"Relatório de {name}", 1, "m")
    data = database.get("reports", report["id"])
    created = datetime(made.year, made.month, made.day, 12, tzinfo=timezone.utc).isoformat()
    data["created_at"] = created
    database.update("reports", report["id"], data)
    return report


@pytest.fixture
def three_months(repositories, database, sample_class):
    made = [
        report_made_on(repositories, database, sample_class, "Alice Martins", date(2025, 7, 10)),
        report_made_on(repositories, database, sample_class, "Bento Oliveira", date(2025, 7, 2)),
        report_made_on(repositories, database, sample_class, "Clara Souza", date(2025, 6, 20)),
        report_made_on(repositories, database, sample_class, "Davi Santos", date(2024, 12, 5)),
    ]
    return made


def month_groups(page):
    """{month key: (header, rows column)} on the report screen."""
    groups = {}
    for column in find_all(page.controls[-1], lambda c: isinstance(c, ft.Column)
                           and str(c.data).startswith("month:")):
        header, rows = column.controls
        groups[column.data.split(":", 1)[1]] = (header, rows)
    return groups


def test_reports_are_grouped_by_month_newest_first(make_page, repositories, sample_class,
                                                    three_months):
    page = make_page()
    open_reports(page, repositories, sample_class)
    groups = month_groups(page)

    assert list(groups) == ["2025-07", "2025-06", "2024-12"]
    titles = [collect_texts(header) for header, _ in groups.values()]
    assert titles == [["July 2025", "2"], ["June 2025", "1"], ["December 2024", "1"]]
    # Only the latest month is open.
    assert [rows.visible for _, rows in groups.values()] == [True, False, False]
    july_rows = groups["2025-07"][1].controls
    assert [r.data for r in july_rows] == [f"report:{three_months[0]['id']}",
                                          f"report:{three_months[1]['id']}"]


def test_tap_a_month_to_show_or_hide_its_reports(make_page, repositories, sample_class,
                                                 three_months):
    page = make_page()
    app = open_reports(page, repositories, sample_class)
    body = layout(page)[0]
    groups = month_groups(page)
    june_header, june_rows = groups["2025-06"]
    july_header, july_rows = groups["2025-07"]

    june_header.on_click(None)
    july_header.on_click(None)

    assert june_rows.visible and not july_rows.visible  # changed in place...
    assert june_header.content.controls[0].icon == ft.Icons.EXPAND_MORE
    assert july_header.content.controls[0].icon == ft.Icons.CHEVRON_RIGHT
    assert layout(page)[0] is body  # ...so the page doesn't move

    app.render()  # e.g. after deleting a report: the choice is kept
    groups = month_groups(page)
    assert [rows.visible for _, rows in groups.values()] == [False, True, False]


def test_months_in_portuguese(make_page, repositories, sample_class, three_months):
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    titles = [collect_texts(header)[0] for header, _ in month_groups(page).values()]
    assert titles == ["Julho de 2025", "Junho de 2025", "Dezembro de 2024"]


@pytest.mark.parametrize(("language", "expected"), [("en", "March 2025"),
                                                    ("pt", "Março de 2025")])
def test_format_month(language, expected):
    assert Translator(language).format_month(date(2025, 3, 15)) == expected
