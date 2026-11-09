"""Tests for language detection and the translation tables."""

import asyncio
import string

import flet as ft
import pytest

import i18n
from i18n import Translator, detect_device_language, resolve_language


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_have_the_same_keys():
    assert i18n.TRANSLATIONS["en"].keys() == i18n.TRANSLATIONS["pt"].keys()


def test_both_languages_use_the_same_placeholders():
    for key, english in i18n.TRANSLATIONS["en"].items():
        assert placeholders(english) == placeholders(i18n.TRANSLATIONS["pt"][key]), key


@pytest.mark.parametrize(
    ("locales", "expected"),
    [
        ([ft.Locale("pt", "BR")], "pt"),
        ([ft.Locale("pt", "PT")], "pt"),
        ([ft.Locale("pt")], "pt"),
        ([ft.Locale("en", "US")], "en"),
        ([ft.Locale("fr")], "en"),
        # Only the primary device language counts.
        ([ft.Locale("es", "ES"), ft.Locale("pt", "BR")], "en"),
        ([], "en"),
        (None, "en"),
    ],
)
def test_resolve_language(locales, expected):
    assert resolve_language(locales) == expected


def test_detect_device_language_reads_the_device_locale(make_page):
    page = make_page([ft.Locale("pt", "BR")])
    assert asyncio.run(detect_device_language(page)) == "pt"


def test_detect_device_language_falls_back_to_english_on_error(make_page):
    page = make_page(device_info_fails=True)
    assert asyncio.run(detect_device_language(page)) == "en"


def test_translator_formats_and_pluralizes():
    en, pt = Translator("en"), Translator("pt")
    assert en.t("dashboard.title") == "Your classes"
    assert pt.t("dashboard.title") == "Suas turmas"
    assert en.plural("dashboard.students_count", 1).startswith("1 child ")
    assert en.plural("dashboard.students_count", 4).startswith("4 children ")
    assert pt.plural("dashboard.students_count", 1).startswith("1 criança ")
    assert pt.plural("dashboard.students_count", 4).startswith("4 crianças ")


def test_translator_falls_back_to_english():
    assert Translator("de").language == "en"
    assert Translator("pt").t("missing.key") == "missing.key"
