"""Tests for events (learning story), encrypted photo files and photo cache cleanup."""

import asyncio
import sqlite3
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

import media
from database import EventValidationError
from database.events import MAX_PHOTOS_PER_EVENT
from database.photos import MAX_PHOTO_BYTES, PhotoStore, image_type
from tests.conftest import JPEG, PNG


@pytest.fixture
def kids(repositories):
    """A class with three children: returns (class id, {name: id})."""
    class_id = repositories.classes.add("Preschool I")["id"]
    ids = {n: repositories.students.add(class_id, n)["id"] for n in ("Alice", "Bento", "Clara")}
    return class_id, ids


# --- events -----------------------------------------------------------------------------


def test_add_event_with_photos(repositories, kids):
    class_id, ids = kids

    event = repositories.events.add(
        class_id, [ids["Alice"], ids["Bento"]], "  Built a tower  ", date(2024, 5, 10), [JPEG, PNG]
    )

    assert event["description"] == "Built a tower"
    assert event["occurred_on"] == date(2024, 5, 10)
    assert sorted(event["student_ids"]) == sorted([ids["Alice"], ids["Bento"]])
    assert [repositories.events.load_photo(p) for p in event["photo_ids"]] == [JPEG, PNG]


def test_photo_only_and_text_only_events_are_valid(repositories, kids):
    class_id, ids = kids
    repositories.events.add(class_id, [ids["Alice"]], "", date.today(), [JPEG])
    repositories.events.add(class_id, [ids["Alice"]], "Only words", date.today())

    assert len(repositories.events.story(ids["Alice"])) == 2


def test_story_is_per_child_and_newest_first(repositories, kids):
    class_id, ids = kids
    old = repositories.events.add(class_id, [ids["Alice"]], "old", date(2024, 1, 1))
    both = [ids["Alice"], ids["Bento"]]
    shared = repositories.events.add(class_id, both, "shared", date(2024, 3, 1))
    same_day_later = repositories.events.add(class_id, [ids["Alice"]], "later", date(2024, 3, 1))

    assert [e["id"] for e in repositories.events.story(ids["Alice"])] == [
        same_day_later["id"], shared["id"], old["id"]
    ]
    assert [e["id"] for e in repositories.events.story(ids["Bento"])] == [shared["id"]]
    assert repositories.events.story(ids["Clara"]) == []
    assert len(repositories.events.story(ids["Alice"], limit=2)) == 2
    assert repositories.events.count_by_student() == {ids["Alice"]: 3, ids["Bento"]: 1}


def test_story_is_kept_when_a_child_is_removed_from_the_class(repositories, kids):
    class_id, ids = kids
    repositories.events.add(class_id, [ids["Alice"]], "First steps", date.today())

    repositories.students.deactivate(ids["Alice"])

    assert [e["description"] for e in repositories.events.story(ids["Alice"])] == ["First steps"]
    with pytest.raises(EventValidationError) as error:  # but no new events for her
        repositories.events.add(class_id, [ids["Alice"]], "Another", date.today())
    assert error.value.code == "unknown_student"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"student_ids": []}, "no_students"),
        ({"student_ids": ["unknown"]}, "unknown_student"),
        ({"student_ids": "other_class"}, "unknown_student"),
        ({"description": "   ", "photos": []}, "empty"),
        ({"description": "x" * 2001}, "description_too_long"),
        ({"occurred_on": date.today() + timedelta(days=1)}, "date_in_future"),
        ({"occurred_on": date(1999, 12, 31)}, "invalid_date"),
        ({"occurred_on": datetime(2024, 1, 1)}, "invalid_date"),
        ({"photos": [JPEG] * (MAX_PHOTOS_PER_EVENT + 1)}, "too_many_photos"),
        ({"photos": [JPEG + b"\x00" * MAX_PHOTO_BYTES]}, "photo_too_large"),
        ({"photos": [b"%PDF-1.7 not a photo"]}, "invalid_photo"),
    ],
)
def test_event_validation(repositories, kids, change, code):
    class_id, ids = kids
    if change.get("student_ids") == "other_class":
        other = repositories.classes.add("Other")["id"]
        change["student_ids"] = [repositories.students.add(other, "Gael")["id"]]
    values = {
        "student_ids": [ids["Alice"]],
        "description": "Nice moment",
        "occurred_on": date.today(),
        "photos": [JPEG],
        **change,
    }

    with pytest.raises(EventValidationError) as error:
        repositories.events.add(class_id, **values)

    assert error.value.code == code
    assert repositories.events.count_by_student() == {}


def test_failed_save_leaves_no_orphan_photo_files(repositories, kids, database, monkeypatch):
    class_id, ids = kids

    def broken_insert(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(database, "insert", broken_insert)
    with pytest.raises(RuntimeError):
        repositories.events.add(class_id, [ids["Alice"]], "x", date.today(), [JPEG, PNG])

    assert list((database.path.parent / "photos").iterdir()) == []


# --- encrypted photo files -------------------------------------------------------------------


def test_events_and_photos_are_encrypted_on_disk(repositories, kids, database):
    class_id, ids = kids
    repositories.events.add(class_id, [ids["Alice"]], "Sorted the red blocks first",
                            date(2024, 5, 10), [JPEG, PNG])

    files = [f for f in database.path.parent.rglob("*") if f.is_file()]
    raw = b"".join(f.read_bytes() for f in files)
    assert len([f for f in files if f.suffix == ".enc"]) == 2
    for secret in (b"Sorted the red blocks", b"2024-05-10", b"jpeg-body", b"png-body",
                   b"\x89PNG", b"\xff\xd8\xff"):
        assert secret not in raw, secret

    # Which children and photos an event is linked to is encrypted too.
    connection = sqlite3.connect(database.path)
    [row] = connection.execute("SELECT * FROM events").fetchall()
    connection.close()
    for value in row:
        stored = value if isinstance(value, bytes) else str(value).encode()
        assert ids["Alice"].encode() not in stored
        assert not any(f.stem.encode() in stored for f in files if f.suffix == ".enc")


def test_photo_files_are_bound_to_their_id(repositories, kids, database):
    class_id, ids = kids
    event = repositories.events.add(class_id, [ids["Alice"]], "", date.today(), [JPEG, PNG])
    first, second = (database.path.parent / "photos" / f"{p}.enc" for p in event["photo_ids"])

    first.write_bytes(second.read_bytes())  # swap a photo file for another one

    assert repositories.events.load_photo(event["photo_ids"][0]) is None
    assert repositories.events.load_photo(event["photo_ids"][1]) == PNG


def test_missing_or_invalid_photo_ids(repositories, database, tmp_path):
    assert repositories.events.load_photo("0" * 32) is None
    # Ids are validated before building a path: no reading outside photos/.
    assert repositories.events.load_photo("../../test") is None
    with pytest.raises(ValueError):
        PhotoStore(tmp_path / "photos", database).delete("../test")
    assert database.path.exists()


def test_photo_store_writes_atomically(database, tmp_path):
    store = PhotoStore(tmp_path / "photos", database)
    photo_id = store.save(JPEG)

    assert [f.name for f in (tmp_path / "photos").iterdir()] == [f"{photo_id}.enc"]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"GIF89a...", "image/gif"),
        (b"\x00\x00\x00\x18ftypheic....", "image/heic"),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_image_type(data, expected):
    assert image_type(data) == expected


# --- photo cache cleanup (media.py) ----------------------------------------------------------


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    cache, temp = tmp_path / "cache", tmp_path / "temp"
    for d in (cache / "file_picker" / "123", temp):
        d.mkdir(parents=True)
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(cache))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(temp))
    return cache, temp


def test_purge_removes_plugin_photo_copies_only_in_packaged_apps(scratch, monkeypatch):
    cache, temp = scratch
    plugin_copies = [cache / "CAP123.jpg", cache / "file_picker" / "123" / "IMG_1.HEIC",
                     temp / "CAP_ABC.jpeg"]
    kept = [cache / "other.jpg", cache / "file_picker" / "123" / "notes.txt", temp / "data.bin"]
    for f in plugin_copies + kept:
        f.write_bytes(b"x")

    assert media.purge_plaintext_media_cache() == 0  # development: never touches files
    assert all(f.exists() for f in plugin_copies)

    monkeypatch.setenv("FLET_PLATFORM", "android")
    assert media.purge_plaintext_media_cache() == 3
    assert not any(f.exists() for f in plugin_copies)
    assert all(f.exists() for f in kept)


def test_discard_copy_only_inside_the_app_scratch_folders(scratch, tmp_path, monkeypatch):
    cache, _ = scratch
    inside = cache / "file_picker" / "123" / "photo.jpg"
    outside = tmp_path / "Pictures" / "photo.jpg"  # e.g. the user's original file
    outside.parent.mkdir()
    for f in (inside, outside):
        f.write_bytes(b"x")
    monkeypatch.setenv("FLET_PLATFORM", "ios")

    media.discard_plaintext_copy(str(outside))
    media.discard_plaintext_copy(str(inside))
    media.discard_plaintext_copy(None)

    assert outside.exists()
    assert not inside.exists()


def test_gallery_picker_returns_bytes_and_discards_copies(scratch, monkeypatch):
    cache, _ = scratch
    copy = cache / "file_picker" / "123" / "IMG_1.jpg"
    copy.write_bytes(JPEG)
    monkeypatch.setenv("FLET_PLATFORM", "android")
    picker = media.GalleryPicker()
    calls = {}

    async def fake_pick_files(**kwargs):
        calls.update(kwargs)
        return [SimpleNamespace(bytes=JPEG, path=str(copy)), SimpleNamespace(bytes=None, path=None)]

    monkeypatch.setattr(picker._picker, "pick_files", fake_pick_files)

    assert asyncio.run(picker.pick_photos()) == [JPEG]
    assert calls["with_data"] is True and calls["allow_multiple"] is True
    assert not copy.exists()


# --- editing events ------------------------------------------------------------------


def photo_files(database):
    return {f.stem for f in (database.path.parent / "photos").glob("*.enc")}


def test_update_event(repositories, kids, database):
    class_id, ids = kids
    event = repositories.events.add(
        class_id, [ids["Alice"]], "Before", date(2024, 1, 1), [JPEG, PNG]
    )
    drop, keep = event["photo_ids"]  # keep the PNG, drop the JPEG

    updated = repositories.events.update(
        event["id"], [ids["Alice"], ids["Bento"]], "  After  ", date(2024, 1, 2), [JPEG, keep]
    )

    assert updated["description"] == "After"
    assert updated["occurred_on"] == date(2024, 1, 2)
    assert sorted(updated["student_ids"]) == sorted([ids["Alice"], ids["Bento"]])
    assert updated["photo_ids"][1] == keep  # kept photo, in the new order
    assert [repositories.events.load_photo(p) for p in updated["photo_ids"]] == [JPEG, PNG]
    assert drop not in photo_files(database)  # removed photo's file deleted
    assert photo_files(database) == set(updated["photo_ids"])
    assert updated["created_at"] == event["created_at"]
    assert repositories.events.get(event["id"]) == updated
    assert repositories.events.story(ids["Bento"]) == [updated]


def test_update_validation(repositories, kids):
    class_id, ids = kids
    event = repositories.events.add(class_id, [ids["Alice"]], "", date.today(), [JPEG])

    def update(**change):
        values = {"student_ids": [ids["Alice"]], "description": "",
                  "occurred_on": date.today(), "photos": event["photo_ids"], **change}
        with pytest.raises(EventValidationError) as error:
            repositories.events.update(event["id"], **values)
        return error.value.code

    assert update(photos=[]) == "empty"  # removing the only photo of a photo-only event
    assert update(student_ids=[]) == "no_students"
    assert update(photos=["f" * 32]) == "invalid_photo"  # not a photo of this event
    assert update(photos=event["photo_ids"] + [JPEG] * MAX_PHOTOS_PER_EVENT) == "too_many_photos"
    assert update(occurred_on=date.today() + timedelta(days=1)) == "date_in_future"
    assert repositories.events.get(event["id"]) == event  # unchanged


def test_update_unknown_event(repositories, kids):
    from database import EventNotFoundError

    class_id, ids = kids
    with pytest.raises(EventNotFoundError):
        repositories.events.update("unknown", [ids["Alice"]], "x", date.today(), [])


def test_update_keeps_transferred_children_but_cannot_add_them(repositories, kids):
    class_id, ids = kids
    event = repositories.events.add(class_id, [ids["Alice"]], "Together", date.today())
    repositories.students.deactivate(ids["Alice"])
    repositories.students.deactivate(ids["Clara"])

    kept = repositories.events.update(event["id"], [ids["Alice"], ids["Bento"]], "Edited",
                                      date.today(), [])
    assert ids["Alice"] in kept["student_ids"]
    with pytest.raises(EventValidationError) as error:
        repositories.events.update(event["id"], [ids["Alice"], ids["Clara"]], "Edited",
                                   date.today(), [])
    assert error.value.code == "unknown_student"


def test_failed_update_keeps_the_old_photos_and_removes_new_ones(
    repositories, kids, database, monkeypatch
):
    class_id, ids = kids
    event = repositories.events.add(class_id, [ids["Alice"]], "x", date.today(), [JPEG])
    before = photo_files(database)

    def broken_update(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(database, "update", broken_update)
    with pytest.raises(RuntimeError):
        repositories.events.update(event["id"], [ids["Alice"]], "x", date.today(), [PNG])

    assert photo_files(database) == before  # old photo kept, new one cleaned up
    assert repositories.events.load_photo(event["photo_ids"][0]) == JPEG
