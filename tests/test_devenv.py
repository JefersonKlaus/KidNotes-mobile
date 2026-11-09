"""Tests for the development .env loader."""

import os

import pytest

from devenv import load_dev_env


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for key in ("KN_PLAIN", "KN_QUOTED", "KN_SINGLE", "KN_EXPORTED", "KN_EMPTY", "KN_SHELL"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "\n"
        "KN_PLAIN=gsk_123\n"
        'KN_QUOTED="with spaces = and equals"\n'
        "KN_SINGLE='single'\n"
        "export KN_EXPORTED=yes\n"
        "KN_EMPTY=\n"
        "KN_SHELL=from-file\n"
        "not a variable\n",
        encoding="utf-8",
    )
    return path


def test_loads_variables(env_file, monkeypatch):
    monkeypatch.setenv("KN_SHELL", "from-shell")

    loaded = load_dev_env(env_file)

    assert os.environ["KN_PLAIN"] == "gsk_123"
    assert os.environ["KN_QUOTED"] == "with spaces = and equals"
    assert os.environ["KN_SINGLE"] == "single"
    assert os.environ["KN_EXPORTED"] == "yes"
    assert os.environ["KN_EMPTY"] == ""
    assert os.environ["KN_SHELL"] == "from-shell"  # the terminal wins
    assert "KN_SHELL" not in loaded


def test_missing_file_is_fine(tmp_path):
    assert load_dev_env(tmp_path / ".env") == {}


def test_ignored_in_packaged_apps(env_file, monkeypatch):
    monkeypatch.setenv("FLET_PLATFORM", "android")
    assert load_dev_env(env_file) == {}
    assert "KN_PLAIN" not in os.environ


def test_example_file_documents_every_variable():
    from pathlib import Path

    example = (Path(__file__).parent.parent / ".env.example").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in example


def test_env_files_are_not_packaged_or_committed():
    from pathlib import Path

    root = Path(__file__).parent.parent
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
