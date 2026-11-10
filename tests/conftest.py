"""Shared test helpers: fake Flet page, isolated storage and database fixtures."""

import asyncio
from typing import Any

import flet as ft
import pytest

from database import ClassRepository, EncryptedDatabase, Repositories
from database.crypto import RecordCipher, generate_key

SAMPLE_STUDENTS = ["Alice Martins", "Bento Oliveira", "Clara Souza", "Davi Santos", "Luna Costa"]

# Smallest valid-looking images (only the header is checked by the app).
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + b"png-body"


class FakeGallery:
    """Stands in for the system photo picker."""

    def __init__(self, photos: list[bytes] | None = None, fails: bool = False) -> None:
        self.photos = photos if photos is not None else [JPEG]
        self.fails = fails

    async def pick_photos(self) -> list[bytes]:
        if self.fails:
            raise RuntimeError("picker failed")
        return list(self.photos)


class FakeCamera:
    """Stands in for flet_camera.Camera (the real one needs a phone)."""

    def __init__(self, photo: bytes = JPEG, available: bool = True) -> None:
        self.photo = photo
        self.available = available
        self.initialized_with = None

    async def get_available_cameras(self):
        if not self.available:
            return []
        import flet_camera as fc

        return [
            fc.CameraDescription(
                name="front", lens_direction=fc.CameraLensDirection.FRONT, sensor_orientation=0
            ),
            fc.CameraDescription(
                name="back", lens_direction=fc.CameraLensDirection.BACK, sensor_orientation=90
            ),
        ]

    async def initialize(self, description, resolution_preset, enable_audio=True, **_):
        self.initialized_with = (description.name, resolution_preset, enable_audio)

    async def take_picture(self) -> bytes:
        return self.photo


class MemoryKeyStore:
    """In-memory replacement for the Keystore/Keychain key store."""

    def __init__(self, value: str | None = None) -> None:
        self.value = value

    async def get(self) -> str | None:
        return self.value

    async def set(self, value: str) -> None:
        self.value = value


class FakePage:
    """Minimal stand-in for `ft.Page`, so screens can be rendered without a Flutter client."""

    def __init__(self, locales: list[ft.Locale] | None = None, device_info_fails: bool = False):
        self.controls: list[ft.Control] = []
        self.overlay: list[ft.Control] = []  # floats over the page (the top notice)
        self.drawer: ft.NavigationDrawer | None = None  # the side menu
        self.drawer_open = False
        self.dialogs: list[ft.DialogControl] = []  # open dialogs, like Flet's dialog stack
        self.dialog_popped = False
        self.platform: ft.PagePlatform | None = None  # None: like a desktop window
        self.web = False
        self.tasks: list[Any] = []  # coroutine functions passed to run_task()
        self.locale_configuration: ft.LocaleConfiguration | None = None
        self._locales = locales
        self._device_info_fails = device_info_fails

    async def get_device_info(self) -> Any:
        if self._device_info_fails:
            raise RuntimeError("device info not supported")
        return type("DeviceInfo", (), {"locales": self._locales})()

    def add(self, *controls: ft.Control) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        pass

    async def show_drawer(self) -> None:
        if self.drawer is None:
            raise ValueError("No drawer defined")  # like Flet
        self.drawer_open = True

    async def close_drawer(self) -> None:
        self.drawer_open = False

    def run_task(self, handler: Any, *args: Any) -> None:
        self.tasks.append((handler, args))

    @property
    def dialog(self) -> ft.DialogControl | None:
        """The topmost open dialog."""
        return self.dialogs[-1] if self.dialogs else None

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> ft.DialogControl | None:
        self.dialog_popped = True
        return self.dialogs.pop() if self.dialogs else None


def collect_texts(control: Any, out: list[str] | None = None) -> list[str]:
    """Return every user-visible string (text, label, hint, tooltip...) in a control tree."""
    out = [] if out is None else out
    for attr in ("value", "label", "hint_text", "tooltip", "content", "title"):
        value = getattr(control, attr, None)
        if isinstance(value, str):
            out.append(value)
    for attr in ("content", "title", "controls", "actions", "label"):
        value = getattr(control, attr, None)
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, ft.Control):
                collect_texts(child, out)
    return out


def find_all(control: Any, predicate: Any) -> list[ft.Control]:
    """All controls in the tree (including `control`) that match `predicate`."""
    found = [control] if isinstance(control, ft.Control) and predicate(control) else []
    for attr in ("content", "controls", "actions", "label"):
        value = getattr(control, attr, None)
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, ft.Control):
                found.extend(find_all(child, predicate))
    return found


def find_button(control: Any, text: str) -> ft.Control:
    """Find a button (or any control) whose `content` text is `text`.

    Also finds buttons with a custom content (e.g. icon above the label) whose
    visible label is `text`.
    """
    content = getattr(control, "content", None)
    if content == text:
        return control
    buttons = (ft.Button, ft.OutlinedButton, ft.TextButton)
    if isinstance(control, buttons) and isinstance(content, ft.Control):
        if text in collect_texts(content):
            return control
    for attr in ("content", "controls", "actions"):
        value = getattr(control, attr, None)
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, ft.Control):
                found = find_button(child, text)
                if found is not None:
                    return found
    return None


def fill(field: ft.TextField, value: str) -> None:
    field.value = value


def auth_fields(page: FakePage) -> dict[str, ft.TextField]:
    """The text fields of the sign-in / registration screen, by label."""
    fields = find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
    return {f.label: f for f in fields}


def sign_up(page: FakePage, email: str = "ana@school.org", password: str = "secret-pass"):
    """Create the account through the registration screen (English)."""
    fields = auth_fields(page)
    fill(fields["Email"], email)
    fill(fields["Password"], password)
    fill(fields["Confirm password"], password)
    find_button(page.controls[-1], "Create account").on_click(None)


def sign_in(page: FakePage, email: str = "ana@school.org", password: str = "secret-pass"):
    fields = auth_fields(page)
    fill(fields["Email"], email)
    fill(fields["Password"], password)
    find_button(page.controls[-1], "Sign in").on_click(None)


def open_menu(page: FakePage) -> ft.NavigationDrawer:
    """Tap ☰ (home) or, on screens without it, swipe from the left edge; return the menu."""
    buttons = find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
                       and c.data == "menu")
    asyncio.run(buttons[0].on_click(None) if buttons else page.show_drawer())
    assert page.drawer_open
    return page.drawer


def side_menu_item(page: FakePage, name: str) -> ft.ListTile:
    """"settings" or "sign_out" in the side menu."""
    [item] = [c for c in page.drawer.controls if getattr(c, "data", None) == f"menu:{name}"]
    return item


def sign_out_from_menu(page: FakePage) -> None:
    open_menu(page)
    asyncio.run(side_menu_item(page, "sign_out").on_click(None))


def notice(page: FakePage) -> ft.Control | None:
    """The information message shown at the top of the screen (or None)."""
    found = [c for c in page.overlay if getattr(c, "data", None) == "notice"]
    return found[-1] if found else None


def notice_text(page: FakePage) -> str | None:
    """Text of the top information message (without the close button)."""
    shown = notice(page)
    if shown is None:
        return None
    return " ".join(t for t in collect_texts(shown) if t)


def notice_is_error(page: FakePage) -> bool:
    shown = notice(page)
    icons = find_all(shown, lambda c: isinstance(c, ft.Icon))
    return icons[0].icon == ft.Icons.ERROR_OUTLINE


def screen_text(page: FakePage) -> str:
    """All visible text of the screen currently rendered on the page."""
    return " | ".join(collect_texts(page.controls[-1]))


@pytest.fixture
def make_page():
    return FakePage


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """scrypt is deliberately slow; tests use a tiny cost (the real one is tested)."""
    import database.accounts

    monkeypatch.setattr(database.accounts, "KDF_N", 2**4)


@pytest.fixture(autouse=True)
def app_storage(tmp_path, monkeypatch):
    """Every test gets its own app data folder and runs in development mode."""
    data_dir = tmp_path / "app-data"
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(data_dir))
    monkeypatch.delenv("FLET_PLATFORM", raising=False)
    return data_dir


@pytest.fixture
def database(tmp_path):
    db = EncryptedDatabase(tmp_path / "test.db", RecordCipher(generate_key()))
    yield db
    db.close()


@pytest.fixture
def class_repository(database):
    return ClassRepository(database)


@pytest.fixture
def repositories(database):
    return Repositories.from_database(database)


@pytest.fixture
def sample_class(repositories):
    """A class stored in the database with five active students."""
    class_data = repositories.classes.add("Preschool I - Morning", "#F8C8D8")
    for name in SAMPLE_STUDENTS:
        repositories.students.add(class_data["id"], name)
    return class_data
