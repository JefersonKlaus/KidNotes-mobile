"""Tests for the encrypted database: crypto, storage at rest, repository and key handling."""

import asyncio
import os
import sqlite3
import threading

import pytest

from database import ClassRepository, ClassValidationError, DatabaseKeyError, EncryptedDatabase
from database.bootstrap import REGISTRY_FILE, load_or_create_key, open_account_store
from database.connection import MIGRATIONS
from database.crypto import (
    DecryptionError,
    RecordCipher,
    decode_key,
    encode_key,
    generate_key,
)
from database.keys import DevFileKeyStore, SecureKeyStore, create_key_store
from tests.conftest import MemoryKeyStore

# --- crypto -------------------------------------------------------------------


def test_cipher_round_trip_and_random_nonce():
    cipher = RecordCipher(generate_key())
    first = cipher.encrypt(b"secret", b"classes:1")
    second = cipher.encrypt(b"secret", b"classes:1")

    assert first != second  # a new nonce for every write
    assert cipher.decrypt(first, b"classes:1") == b"secret"


def test_cipher_rejects_wrong_key_tampering_and_other_locations():
    cipher = RecordCipher(generate_key())
    blob = cipher.encrypt(b"secret", b"classes:1")
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])

    with pytest.raises(DecryptionError):
        RecordCipher(generate_key()).decrypt(blob, b"classes:1")
    with pytest.raises(DecryptionError):
        cipher.decrypt(tampered, b"classes:1")
    with pytest.raises(DecryptionError):
        cipher.decrypt(blob, b"classes:2")  # moved to another record
    with pytest.raises(DecryptionError):
        cipher.decrypt(b"short", b"classes:1")


def test_key_encoding():
    key = generate_key()
    assert len(key) == 32
    assert decode_key(encode_key(key)) == key
    with pytest.raises(ValueError):
        decode_key(encode_key(b"too short"))
    with pytest.raises(ValueError):
        RecordCipher(b"too short")


# --- data at rest --------------------------------------------------------------


def test_no_plain_text_is_written_to_disk(tmp_path):
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))
    repository = ClassRepository(db)
    repository.add("Turma Secreta Girassol", "#C9B8E8")
    db.close()

    raw = b"".join(f.read_bytes() for f in tmp_path.rglob("*") if f.is_file())  # db + journal files
    for secret in ("Turma Secreta Girassol", "Girassol", "C9B8E8", "created_at", '"name"'):
        assert secret.encode() not in raw, secret
        assert secret.encode("utf-16-le") not in raw, secret


def test_data_persists_when_reopened_with_the_same_key(tmp_path):
    key = generate_key()
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key))
    saved = ClassRepository(db).add("Preschool I", "#F8C8D8")
    db.close()

    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(key))
    assert ClassRepository(db).list_all() == [saved]
    db.close()


def test_opening_with_another_key_fails(tmp_path):
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))
    ClassRepository(db).add("Preschool I")
    db.close()

    with pytest.raises(DatabaseKeyError):
        EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))


def test_swapped_or_corrupted_records_are_skipped(tmp_path):
    db = EncryptedDatabase(tmp_path / "kidnotes.db", RecordCipher(generate_key()))
    repository = ClassRepository(db)
    first = repository.add("First")
    second = repository.add("Second")
    db.close()

    raw = sqlite3.connect(tmp_path / "kidnotes.db")
    with raw:  # copy the encrypted payload of `first` into `second`
        raw.execute(
            "UPDATE classes SET payload = (SELECT payload FROM classes WHERE id = ?) WHERE id = ?",
            (first["id"], second["id"]),
        )
    raw.close()

    db = EncryptedDatabase(tmp_path / "kidnotes.db", db._cipher)
    assert [c["name"] for c in ClassRepository(db).list_all()] == ["First"]
    db.close()


def test_schema_version_is_recorded(database):
    version = database._connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(MIGRATIONS) == 4


# --- class repository ----------------------------------------------------------


def test_add_and_list_classes_in_creation_order(class_repository):
    a = class_repository.add("Preschool I", "#F8C8D8")
    b = class_repository.add("Preschool II", "#B8DCEB")

    assert class_repository.list_all() == [a, b]
    assert a["id"] != b["id"]
    assert class_repository.get(a["id"]) == a
    assert class_repository.get("unknown") is None


@pytest.mark.parametrize(
    ("name", "color", "code"),
    [
        ("", "#F8C8D8", "name_required"),
        ("   ", "#F8C8D8", "name_required"),
        ("x" * 61, "#F8C8D8", "name_too_long"),
        ("Preschool", "red", "invalid_color"),
    ],
)
def test_class_validation(class_repository, name, color, code):
    with pytest.raises(ClassValidationError) as error:
        class_repository.add(name, color)
    assert error.value.code == code
    assert class_repository.list_all() == []


def test_class_name_is_trimmed(class_repository):
    assert class_repository.add("  Preschool   I  ")["name"] == "Preschool I"


def test_repository_works_from_worker_threads(class_repository):
    # Flet runs sync event handlers in a thread pool.
    errors = []

    def worker(n):
        try:
            class_repository.add(f"Class {n}")
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(class_repository.list_all()) == 8


def test_unknown_tables_are_rejected(database):
    with pytest.raises(ValueError):
        database.insert("sqlite_master", "x", {})


# --- encryption key -------------------------------------------------------------


def test_first_start_creates_and_stores_the_device_key(tmp_path):
    store = MemoryKeyStore()
    accounts = asyncio.run(open_account_store(tmp_path, store))

    assert decode_key(store.value)  # a valid 256-bit key was saved
    assert not accounts.has_accounts()
    accounts.close()


def test_next_starts_reuse_the_stored_device_key(tmp_path):
    store = MemoryKeyStore()
    accounts = asyncio.run(open_account_store(tmp_path, store))
    accounts.register("ana@school.org", "secret-pass", "secret-pass").close()
    accounts.close()
    key = store.value

    accounts = asyncio.run(open_account_store(tmp_path, store))
    assert accounts.has_accounts()
    assert store.value == key
    accounts.close()


def test_a_new_device_key_is_never_created_over_existing_data(tmp_path):
    asyncio.run(open_account_store(tmp_path, MemoryKeyStore())).close()

    empty_store = MemoryKeyStore()  # e.g. the Keystore entry was lost
    with pytest.raises(DatabaseKeyError):
        asyncio.run(load_or_create_key(empty_store, tmp_path / REGISTRY_FILE))
    with pytest.raises(DatabaseKeyError):
        asyncio.run(open_account_store(tmp_path, empty_store))
    assert empty_store.value is None


def test_invalid_stored_key_is_reported(tmp_path):
    with pytest.raises(DatabaseKeyError):
        asyncio.run(open_account_store(tmp_path, MemoryKeyStore("not-a-key")))


def test_dev_key_file_is_private(tmp_path):
    store = DevFileKeyStore(tmp_path / "keys" / "dev.key")
    asyncio.run(store.set("value"))

    assert asyncio.run(store.get()) == "value"
    if os.name == "posix":
        assert (store.path.stat().st_mode & 0o777) == 0o600


def test_packaged_app_uses_the_os_secure_storage(tmp_path, monkeypatch):
    monkeypatch.delenv("FLET_PLATFORM", raising=False)
    assert isinstance(create_key_store(tmp_path), DevFileKeyStore)

    for platform in ("android", "ios"):
        monkeypatch.setenv("FLET_PLATFORM", platform)
        assert isinstance(create_key_store(tmp_path), SecureKeyStore)
