"""Tests for students, settings, the v1 -> v2 migration and the date helpers."""

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from database import (
    EncryptedDatabase,
    Repositories,
    StudentNotFoundError,
    StudentValidationError,
)
from database.connection import MIGRATIONS
from database.crypto import RecordCipher, generate_key
from database.students import initials
from dates import age_in_months, to_local_date
from i18n import Translator

# --- student repository --------------------------------------------------------------


@pytest.fixture
def class_id(repositories):
    return repositories.classes.add("Preschool I")["id"]


def test_add_student(repositories, class_id):
    student = repositories.students.add(class_id, "  Maya   Rocha ", date(2021, 8, 5))

    assert student["name"] == "Maya Rocha"
    assert student["birth_date"] == date(2021, 8, 5)
    assert student["active"] is True
    assert student["class_id"] == class_id
    assert student["initials"] == "MR"
    assert repositories.students.get(student["id"]) == student


def test_students_are_listed_per_class_in_alphabetical_order(repositories, class_id):
    other_class = repositories.classes.add("Preschool II")["id"]
    for name in ["Luna Costa", "álvaro Lima", "Alice Martins", "Bento Oliveira"]:
        repositories.students.add(class_id, name)
    repositories.students.add(other_class, "Gael Lima")

    names = [s["name"] for s in repositories.students.list_active(class_id)]

    assert names == ["Alice Martins", "álvaro Lima", "Bento Oliveira", "Luna Costa"]
    assert [s["name"] for s in repositories.students.list_active(other_class)] == ["Gael Lima"]


@pytest.mark.parametrize(
    ("name", "birth_date", "code"),
    [
        ("", None, "name_required"),
        ("   ", None, "name_required"),
        ("x" * 81, None, "name_too_long"),
        ("Maya", date.today() + timedelta(days=1), "birth_date_in_future"),
        ("Maya", date(1899, 12, 31), "invalid_birth_date"),
        ("Maya", datetime(2021, 8, 5), "invalid_birth_date"),  # must be a date, not a datetime
    ],
)
def test_student_validation(repositories, class_id, name, birth_date, code):
    with pytest.raises(StudentValidationError) as error:
        repositories.students.add(class_id, name, birth_date)
    assert error.value.code == code
    assert repositories.students.list_active(class_id) == []


def test_student_born_today_is_valid(repositories, class_id):
    newborn = repositories.students.add(class_id, "Newborn", date.today())
    assert newborn["birth_date"] == date.today()


def test_add_student_to_unknown_class_fails(repositories):
    with pytest.raises(StudentNotFoundError):
        repositories.students.add("unknown-class", "Maya")


def test_update_student(repositories, class_id):
    student = repositories.students.add(class_id, "Maya", date(2021, 8, 5))

    updated = repositories.students.update(student["id"], "Maya Rocha", None)

    assert updated["name"] == "Maya Rocha"
    assert updated["birth_date"] is None
    assert updated["created_at"] == student["created_at"]
    assert updated["updated_at"] >= student["updated_at"]
    assert repositories.students.get(student["id"]) == updated


def test_update_validates_and_requires_an_existing_student(repositories, class_id):
    student = repositories.students.add(class_id, "Maya")
    with pytest.raises(StudentValidationError):
        repositories.students.update(student["id"], " ", None)
    with pytest.raises(StudentNotFoundError):
        repositories.students.update("unknown", "Maya", None)
    assert repositories.students.get(student["id"])["name"] == "Maya"


def test_deactivate_keeps_the_record_but_hides_it(repositories, class_id):
    student = repositories.students.add(class_id, "Maya")
    repositories.students.add(class_id, "Noah")

    removed = repositories.students.deactivate(student["id"])

    assert removed["active"] is False
    assert removed["deactivated_at"] is not None
    assert repositories.students.get(student["id"])["active"] is False  # not deleted
    assert [s["name"] for s in repositories.students.list_active(class_id)] == ["Noah"]
    assert repositories.students.count_active_by_class() == {class_id: 1}
    # Removing twice is harmless and keeps the first removal date.
    again = repositories.students.deactivate(student["id"])
    assert again["deactivated_at"] == removed["deactivated_at"]
    with pytest.raises(StudentNotFoundError):
        repositories.students.deactivate("unknown")


def test_transferred_students_and_reactivation(repositories, class_id):
    other_class = repositories.classes.add("Preschool II")["id"]
    maya = repositories.students.add(class_id, "Maya")
    noah = repositories.students.add(class_id, "Noah")
    repositories.students.add(other_class, "Gael")
    repositories.students.deactivate(noah["id"])
    repositories.students.deactivate(maya["id"])

    assert [s["name"] for s in repositories.students.list_inactive(class_id)] == ["Maya", "Noah"]
    assert repositories.students.list_inactive(other_class) == []

    back = repositories.students.reactivate(maya["id"])

    assert back["active"] is True and back["deactivated_at"] is None
    assert [s["name"] for s in repositories.students.list_active(class_id)] == ["Maya"]
    assert [s["name"] for s in repositories.students.list_inactive(class_id)] == ["Noah"]
    assert repositories.students.reactivate(maya["id"]) == repositories.students.get(maya["id"])
    with pytest.raises(StudentNotFoundError):
        repositories.students.reactivate("unknown")


def test_reactivated_student_can_be_linked_to_events_again(repositories, class_id):
    maya = repositories.students.add(class_id, "Maya")
    repositories.students.deactivate(maya["id"])
    repositories.students.reactivate(maya["id"])

    event = repositories.events.add(class_id, [maya["id"]], "Back with us", date.today())

    assert repositories.events.story(maya["id"]) == [event]


def test_extra_information(repositories, class_id):
    student = repositories.students.add(class_id, "Maya")
    assert student["notes"] == ""

    saved = repositories.students.update_notes(student["id"], "  Loves sleeping after lunch.  ")

    assert saved["notes"] == "Loves sleeping after lunch."
    assert repositories.students.get(student["id"])["notes"] == "Loves sleeping after lunch."
    assert saved["name"] == "Maya"  # the rest of the record is unchanged
    with pytest.raises(StudentValidationError) as error:
        repositories.students.update_notes(student["id"], "x" * 4001)
    assert error.value.code == "notes_too_long"
    with pytest.raises(StudentNotFoundError):
        repositories.students.update_notes("unknown", "x")
    # Editing the name keeps the notes.
    repositories.students.update(student["id"], "Maya Rocha", None)
    assert repositories.students.get(student["id"])["notes"] == "Loves sleeping after lunch."


def test_extra_information_is_encrypted_on_disk(tmp_path):
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))
    repos = Repositories.from_database(db)
    student = repos.students.add(repos.classes.add("Preschool I")["id"], "Maya")
    repos.students.update_notes(student["id"], "Adora jogar futebol com o Theo")
    db.close()

    raw = b"".join(f.read_bytes() for f in tmp_path.rglob("*") if f.is_file())
    assert b"futebol" not in raw and b"Theo" not in raw


def test_count_active_by_class(repositories, class_id):
    other = repositories.classes.add("Preschool II")["id"]
    for name in ["A", "B", "C"]:
        repositories.students.add(class_id, name)
    repositories.students.add(other, "D")

    assert repositories.students.count_active_by_class() == {class_id: 3, other: 1}


def test_student_data_is_encrypted_on_disk(tmp_path):
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))
    repos = Repositories.from_database(db)
    class_id = repos.classes.add("Preschool I")["id"]
    student = repos.students.add(class_id, "Helena Girassol", date(2021, 8, 5))
    repos.students.deactivate(student["id"])
    db.close()

    raw = b"".join(f.read_bytes() for f in tmp_path.rglob("*") if f.is_file())
    for secret in ("Helena Girassol", "Girassol", "2021-08-05", "active", "birth_date"):
        assert secret.encode() not in raw, secret

    # Which class a student belongs to is encrypted too: the students table
    # only has the random student id and the ciphertext.
    connection = sqlite3.connect(tmp_path / "kidnotes.db")
    rows = connection.execute("SELECT * FROM students").fetchall()
    connection.close()
    assert len(rows) == 1
    for value in rows[0]:
        stored = value if isinstance(value, bytes) else str(value).encode()
        assert class_id.encode() not in stored


def test_avatar_helpers():
    assert initials("Maya Rocha da Silva") == "MS"
    assert initials("maya") == "M"
    assert initials("") == "?"


def test_avatar_color_is_stable(repositories, class_id):
    student = repositories.students.add(class_id, "Maya")
    assert repositories.students.get(student["id"])["color"] == student["color"]


# --- settings ---------------------------------------------------------------------------


def test_last_class_setting(repositories):
    assert repositories.settings.get_last_class_id() is None

    repositories.settings.set_last_class_id("class-1")
    repositories.settings.set_last_class_id("class-2")  # overwritten, not duplicated

    assert repositories.settings.get_last_class_id() == "class-2"


# --- migration --------------------------------------------------------------------------


def test_version_1_database_is_upgraded_without_losing_data(tmp_path, monkeypatch):
    import database.connection as connection

    key = generate_key()
    monkeypatch.setattr(connection, "MIGRATIONS", MIGRATIONS[:1])  # the released v1 schema
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key))
    existing = Repositories.from_database(db).classes.add("Created with v1")
    db.close()
    monkeypatch.setattr(connection, "MIGRATIONS", MIGRATIONS)

    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key))
    repos = Repositories.from_database(db)

    assert repos.classes.list_all() == [existing]
    repos.students.add(existing["id"], "Maya")
    assert db._connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    db.close()


def test_failed_migration_is_rolled_back(tmp_path, monkeypatch):
    import database.connection as connection

    key = generate_key()
    EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key)).close()
    broken = "CREATE TABLE half_done (x); CREATE TABLE broken (;"
    monkeypatch.setattr(connection, "MIGRATIONS", [*MIGRATIONS, broken])

    with pytest.raises(sqlite3.Error):
        EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key))

    raw = sqlite3.connect(tmp_path / "kidnotes.db")
    # Stays on the last good version.
    assert raw.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_done" not in tables  # nothing from the failed migration was kept
    raw.close()


# --- dates ------------------------------------------------------------------------------


@pytest.fixture
def sao_paulo_timezone(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_to_local_date_uses_the_device_timezone(sao_paulo_timezone):
    # Midnight of Aug 5 in São Paulo (UTC-3) is 03:00 UTC: still Aug 5 locally.
    assert to_local_date(datetime(2021, 8, 5, 3, 0, tzinfo=timezone.utc)) == date(2021, 8, 5)
    # 01:00 UTC is still Aug 4 in São Paulo.
    assert to_local_date(datetime(2021, 8, 5, 1, 0, tzinfo=timezone.utc)) == date(2021, 8, 4)


def test_to_local_date_other_inputs():
    assert to_local_date(None) is None
    assert to_local_date("") is None
    assert to_local_date(date(2021, 8, 5)) == date(2021, 8, 5)
    assert to_local_date(datetime(2021, 8, 5, 0, 0)) == date(2021, 8, 5)
    assert to_local_date("2021-08-05T00:00:00") == date(2021, 8, 5)


@pytest.mark.parametrize(
    ("birth", "today", "months"),
    [
        (date(2021, 8, 5), date(2021, 8, 5), 0),
        (date(2021, 8, 5), date(2021, 9, 4), 0),
        (date(2021, 8, 5), date(2021, 9, 5), 1),
        (date(2021, 8, 5), date(2024, 8, 4), 35),
        (date(2021, 8, 5), date(2024, 8, 5), 36),
        (date(2020, 2, 29), date(2021, 2, 28), 11),
        (date(2021, 8, 5), date(2020, 1, 1), 0),  # never negative
    ],
)
def test_age_in_months(birth, today, months):
    assert age_in_months(birth, today) == months


@pytest.mark.parametrize(
    ("language", "birth", "expected"),
    [
        ("en", date(2024, 1, 10), "1 month old"),
        ("en", date(2023, 6, 10), "8 months old"),
        ("en", date(2023, 1, 10), "1 year old"),
        ("en", date(2021, 1, 10), "3 years old"),
        ("pt", date(2024, 1, 10), "1 mês"),
        ("pt", date(2023, 6, 10), "8 meses"),
        ("pt", date(2023, 1, 10), "1 ano"),
        ("pt", date(2021, 1, 10), "3 anos"),
    ],
)
def test_format_age(language, birth, expected):
    assert Translator(language).format_age(birth, today=date(2024, 2, 15)) == expected


def test_format_date():
    assert Translator("en").format_date(date(2021, 8, 5)) == "08/05/2021"
    assert Translator("pt").format_date(date(2021, 8, 5)) == "05/08/2021"


def test_default_class_setting(repositories):
    assert repositories.settings.get_default_class_id() is None
    repositories.settings.set_last_class_id("from-an-older-version")
    assert repositories.settings.get_default_class_id() == "from-an-older-version"

    repositories.settings.set_default_class_id("class-1")
    repositories.settings.set_default_class_id("class-2")  # overwritten

    assert repositories.settings.get_default_class_id() == "class-2"

