"""Tests for local accounts: registration, sign-in and per-account encryption.

These check the security properties on the raw files: the password is never
stored, and a teacher's data and photos can only be decrypted with the key
that their password unlocks (not with the device key alone).
"""

import asyncio
from datetime import date

import pytest

import database.accounts as accounts_module
from database import AccountError, DatabaseKeyError, EncryptedDatabase, Repositories
from database.accounts import ACCOUNT_DATABASE, AccountStore
from database.bootstrap import open_account_store
from database.crypto import DecryptionError, RecordCipher, decode_key
from tests.conftest import JPEG, MemoryKeyStore

PASSWORD = "correct horse battery"


@pytest.fixture
def key_store():
    return MemoryKeyStore()


@pytest.fixture
def accounts(tmp_path, key_store):
    store = asyncio.run(open_account_store(tmp_path, key_store))
    yield store
    store.close()


def device_cipher(key_store):
    return RecordCipher(decode_key(key_store.value))


def all_bytes(folder):
    return b"".join(f.read_bytes() for f in folder.rglob("*") if f.is_file())


# --- registration and sign in --------------------------------------------------------


def test_register_then_sign_in(accounts):
    session = accounts.register(" Ana@School.ORG ", PASSWORD, PASSWORD)
    assert session.email == "ana@school.org"
    Repositories.from_database(session.database).classes.add("Preschool I")
    session.close()

    again = accounts.login("ana@school.org", PASSWORD)

    assert again.account_id == session.account_id
    assert [c["name"] for c in Repositories.from_database(again.database).classes.list_all()] == [
        "Preschool I"
    ]
    again.close()


@pytest.mark.parametrize(
    ("email", "password", "confirmation", "code"),
    [
        ("ana", PASSWORD, PASSWORD, "invalid_email"),
        ("ana@school", PASSWORD, PASSWORD, "invalid_email"),
        ("a na@school.org", PASSWORD, PASSWORD, "invalid_email"),
        ("ana@school.org", "1234567", "1234567", "password_too_short"),
        ("ana@school.org", "x" * 257, "x" * 257, "password_too_long"),
        ("ana@school.org", PASSWORD, PASSWORD + "!", "passwords_dont_match"),
    ],
)
def test_registration_validation(accounts, email, password, confirmation, code):
    with pytest.raises(AccountError) as error:
        accounts.register(email, password, confirmation)
    assert error.value.code == code
    assert not accounts.has_accounts()


def test_email_is_unique_per_device(accounts):
    accounts.register("ana@school.org", PASSWORD, PASSWORD).close()
    with pytest.raises(AccountError) as error:
        accounts.register("ANA@school.org", "other password", "other password")
    assert error.value.code == "email_taken"


@pytest.mark.parametrize(("email", "password"), [
    ("ana@school.org", "wrong password"),
    ("nobody@school.org", PASSWORD),
])
def test_wrong_credentials(accounts, email, password):
    accounts.register("ana@school.org", PASSWORD, PASSWORD).close()
    with pytest.raises(AccountError) as error:
        accounts.login(email, password)
    assert error.value.code == "wrong_credentials"


def test_unknown_email_costs_the_same_work(accounts, monkeypatch):
    """No timing hint about which emails have an account: scrypt runs anyway."""
    accounts.register("ana@school.org", PASSWORD, PASSWORD).close()
    calls = []
    real = accounts_module._derive_key
    monkeypatch.setattr(accounts_module, "_derive_key", lambda *a: calls.append(a) or real(*a))

    for email in ("ana@school.org", "nobody@school.org"):
        with pytest.raises(AccountError):
            accounts.login(email, "wrong password")

    assert len(calls) == 2


def test_password_hashing_cost(accounts, monkeypatch):
    assert accounts_module.RECOMMENDED_KDF_N >= 2**15
    monkeypatch.setattr(accounts_module, "KDF_N", accounts_module.RECOMMENDED_KDF_N)
    session = accounts.register("ana@school.org", PASSWORD, PASSWORD)
    session.close()

    [(_, data)] = list(accounts._registry.iter_records("accounts"))
    assert data["kdf"] == {"name": "scrypt", "n": 2**15, "r": 8, "p": 1}
    # Only the wrapped key is kept: no password, no password hash.
    assert set(data) == {"email", "salt", "kdf", "wrapped_key", "created_at", "last_sign_in_at"}
    accounts.login("ana@school.org", PASSWORD).close()  # works with the real cost


def test_sign_in_uses_the_cost_stored_with_the_account(accounts, monkeypatch):
    accounts.register("ana@school.org", PASSWORD, PASSWORD).close()
    monkeypatch.setattr(accounts_module, "KDF_N", 2**5)  # raised later, for new accounts

    accounts.login("ana@school.org", PASSWORD).close()


# --- encryption ----------------------------------------------------------------------


def test_password_and_email_never_reach_the_disk_in_plain_text(accounts, tmp_path):
    session = accounts.register("ana@school.org", PASSWORD, PASSWORD)
    session.close()

    raw = all_bytes(tmp_path)
    for secret in (PASSWORD, "correct horse", "ana@school.org", "school.org"):
        assert secret.encode() not in raw, secret
        assert secret.encode("utf-16-le") not in raw, secret


def test_teacher_data_needs_the_password_not_just_the_device_key(accounts, tmp_path, key_store):
    session = accounts.register("ana@school.org", PASSWORD, PASSWORD)
    repos = Repositories.from_database(session.database)
    class_id = repos.classes.add("Preschool I")["id"]
    child = repos.students.add(class_id, "Maya Rocha")
    event = repos.events.add(class_id, [child["id"]], "Painted a sun", date.today(), [JPEG])
    session.close()
    folder = accounts.account_dir(session.account_id)

    # The device key (Keystore/Keychain) alone can't open the data...
    with pytest.raises(DatabaseKeyError):
        EncryptedDatabase(folder / ACCOUNT_DATABASE, device_cipher(key_store))
    # ...nor the photos.
    photo = folder / "photos" / f"{event['photo_ids'][0]}.enc"
    with pytest.raises(DecryptionError):
        device_cipher(key_store).decrypt(photo.read_bytes(), f"photos:{photo.stem}".encode())
    # Nothing readable on disk.
    raw = all_bytes(tmp_path)
    for secret in (b"Preschool I", b"Maya Rocha", b"Painted a sun", b"jpeg-body"):
        assert secret not in raw, secret


def test_accounts_cannot_open_each_others_data(accounts):
    ana = accounts.register("ana@school.org", PASSWORD, PASSWORD)
    Repositories.from_database(ana.database).classes.add("Ana's class")
    ana.close()
    bia = accounts.register("bia@school.org", "bia password", "bia password")

    assert Repositories.from_database(bia.database).classes.list_all() == []
    with pytest.raises(DatabaseKeyError):  # Bia's key doesn't open Ana's database
        EncryptedDatabase(accounts.account_dir(ana.account_id) / ACCOUNT_DATABASE,
                          bia.database._cipher)
    bia.close()


def test_failed_registration_leaves_nothing_behind(accounts, monkeypatch):
    def broken_insert(*_):
        raise RuntimeError("disk full")

    monkeypatch.setattr(accounts._registry, "insert", broken_insert)
    with pytest.raises(RuntimeError):
        accounts.register("ana@school.org", PASSWORD, PASSWORD)

    assert not accounts.has_accounts()
    assert list((accounts.data_dir / "accounts").iterdir()) == []


# --- data created before accounts ------------------------------------------------------


def test_existing_data_is_moved_into_the_first_account(tmp_path, key_store):
    # Data saved by the previous version: one database encrypted with the device key.
    accounts = asyncio.run(open_account_store(tmp_path, key_store))
    accounts.close()
    legacy = EncryptedDatabase(tmp_path / "kidnotes.db", device_cipher(key_store))
    repos = Repositories.from_database(legacy)
    class_id = repos.classes.add("Old class")["id"]
    child = repos.students.add(class_id, "Old child")
    old_event = repos.events.add(class_id, [child["id"]], "Old moment", date.today(), [JPEG])
    legacy.close()

    accounts = asyncio.run(open_account_store(tmp_path, key_store))
    session = accounts.register("ana@school.org", PASSWORD, PASSWORD)

    repos = Repositories.from_database(session.database)
    assert [c["name"] for c in repos.classes.list_all()] == ["Old class"]
    assert repos.events.story(child["id"])[0]["description"] == "Old moment"
    assert repos.events.load_photo(old_event["photo_ids"][0]) == JPEG
    # The old files are gone, and the moved data now needs the password.
    assert not (tmp_path / "kidnotes.db").exists()
    assert not (tmp_path / "photos").exists()
    session.close()
    with pytest.raises(DatabaseKeyError):
        EncryptedDatabase(accounts.account_dir(session.account_id) / ACCOUNT_DATABASE,
                          device_cipher(key_store))

    # A second account starts empty.
    bia = accounts.register("bia@school.org", "bia password", "bia password")
    assert Repositories.from_database(bia.database).classes.list_all() == []
    bia.close()
    accounts.close()


def test_store_is_reopened_with_the_same_device_key(tmp_path, key_store):
    first = asyncio.run(open_account_store(tmp_path, key_store))
    first.register("ana@school.org", PASSWORD, PASSWORD).close()
    first.close()

    second = asyncio.run(open_account_store(tmp_path, key_store))
    assert isinstance(second, AccountStore) and second.has_accounts()
    second.login("ana@school.org", PASSWORD).close()
    second.close()


# --- remembering the email for the sign-in screen -----------------------------------------


def test_last_email_is_the_account_that_signed_in_last(accounts):
    assert accounts.last_email() is None
    accounts.register("ana@school.org", PASSWORD, PASSWORD).close()
    assert accounts.last_email() == "ana@school.org"
    accounts.register("bia@school.org", "bia password", "bia password").close()
    assert accounts.last_email() == "bia@school.org"

    accounts.login("ana@school.org", PASSWORD).close()
    assert accounts.last_email() == "ana@school.org"
    with pytest.raises(AccountError):  # a failed attempt doesn't change it
        accounts.login("bia@school.org", "wrong password")
    assert accounts.last_email() == "ana@school.org"
