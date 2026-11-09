"""Local teacher accounts (email + password) and per-account encryption keys.

Everything stays on the device (there is no server). Key hierarchy:

    device key (Android Keystore / iOS Keychain)
      └─ encrypts accounts.db: email, password salt, wrapped account key
    password ──scrypt──► key-encryption key
      └─ unwraps the account key (random AES-256)
           └─ encrypts the account's data: accounts/<id>/kidnotes.db + photos/

So a teacher's data, photos included, can only be decrypted after signing in
with their password. The password itself is never stored: a wrong password
simply fails to unwrap the account key.

There is no way to recover a forgotten password: the data of that account can
no longer be decrypted (the registration screen says so).
"""

import base64
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from database.connection import (
    ACCOUNTS_SCHEMA,
    EncryptedDatabase,
    has_encrypted_data,
)
from database.crypto import DecryptionError, RecordCipher, generate_key

TABLE = "accounts"
ACCOUNTS_DIR = "accounts"
ACCOUNT_DATABASE = "kidnotes.db"
PHOTOS_DIR = "photos"
LEGACY_DATABASE = "kidnotes.db"  # data created before accounts existed

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 256
EMAIL_MAX_LENGTH = 254
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# scrypt cost: ~32 MB of memory and a fraction of a second per sign-in, which
# makes guessing passwords very slow. Stored per account, so it can be raised.
RECOMMENDED_KDF_N = 2**15
KDF_N = RECOMMENDED_KDF_N
KDF_R = 8
KDF_P = 1


class AccountError(ValueError):
    """Sign-in / registration problem. `code` identifies it (for UI messages)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Session:
    """A signed-in teacher: their decrypted data is available until `close()`."""

    account_id: str
    email: str
    database: EncryptedDatabase

    def close(self) -> None:
        self.database.close()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))


def _key_aad(account_id: str) -> bytes:
    return f"account-key:{account_id}".encode()


class AccountStore:
    def __init__(self, registry: EncryptedDatabase, data_dir: Path, device_cipher: RecordCipher):
        self._registry = registry
        self.data_dir = data_dir
        self._device_cipher = device_cipher

    def close(self) -> None:
        self._registry.close()

    def has_accounts(self) -> bool:
        return any(True for _ in self._registry.iter_records(TABLE))

    def last_email(self) -> str | None:
        """Email of the account that signed in last on this device (fills the sign-in form)."""
        accounts = [data for _, data in self._registry.iter_records(TABLE) if data is not None]
        if not accounts:
            return None
        latest = max(accounts, key=lambda d: d.get("last_sign_in_at") or d["created_at"])
        return latest["email"]

    def _mark_signed_in(self, account_id: str, data: dict[str, Any]) -> None:
        data["last_sign_in_at"] = datetime.now(timezone.utc).isoformat()
        self._registry.update(TABLE, account_id, data)

    def account_dir(self, account_id: str) -> Path:
        return self.data_dir / ACCOUNTS_DIR / account_id

    # --- registration -------------------------------------------------------------

    def register(self, email: str, password: str, confirmation: str) -> Session:
        email = normalize_email(email)
        if not _EMAIL.match(email) or len(email) > EMAIL_MAX_LENGTH:
            raise AccountError("invalid_email")
        if len(password) < PASSWORD_MIN_LENGTH:
            raise AccountError("password_too_short")
        if len(password) > PASSWORD_MAX_LENGTH:
            raise AccountError("password_too_long")
        if password != confirmation:
            raise AccountError("passwords_dont_match")
        first_account = not self.has_accounts()
        if not first_account and self._find(email) is not None:
            raise AccountError("email_taken")

        account_id = uuid.uuid4().hex
        account_key = generate_key()
        salt = os.urandom(16)
        wrapping_key = _derive_key(password, salt, KDF_N, KDF_R, KDF_P)
        wrapped = RecordCipher(wrapping_key).encrypt(account_key, _key_aad(account_id))

        folder = self.account_dir(account_id)
        folder.mkdir(parents=True, exist_ok=True)
        adopted = first_account and self._adopt_legacy_data(folder, account_key)
        database = EncryptedDatabase(folder / ACCOUNT_DATABASE, RecordCipher(account_key))
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._registry.insert(
                TABLE,
                account_id,
                {
                    "email": email,
                    "salt": _b64(salt),
                    "kdf": {"name": "scrypt", "n": KDF_N, "r": KDF_R, "p": KDF_P},
                    "wrapped_key": _b64(wrapped),
                    "created_at": now,
                    "last_sign_in_at": now,
                },
            )
        except Exception:
            database.close()
            shutil.rmtree(folder, ignore_errors=True)
            raise
        if adopted:
            self._remove_legacy_data()
        return Session(account_id, email, database)

    # --- sign in ------------------------------------------------------------------

    def login(self, email: str, password: str) -> Session:
        found = self._find(normalize_email(email))
        if found is None:
            # Same work as a real attempt: the time taken doesn't reveal
            # whether an email has an account on this device.
            _derive_key(password, b"\0" * 16, KDF_N, KDF_R, KDF_P)
            raise AccountError("wrong_credentials")
        account_id, data = found
        kdf = data["kdf"]
        wrapping_key = _derive_key(password, _unb64(data["salt"]), kdf["n"], kdf["r"], kdf["p"])
        try:
            account_key = RecordCipher(wrapping_key).decrypt(
                _unb64(data["wrapped_key"]), _key_aad(account_id)
            )
        except DecryptionError:
            raise AccountError("wrong_credentials") from None
        folder = self.account_dir(account_id)
        folder.mkdir(parents=True, exist_ok=True)
        database = EncryptedDatabase(folder / ACCOUNT_DATABASE, RecordCipher(account_key))
        self._mark_signed_in(account_id, data)
        return Session(account_id, data["email"], database)

    def _find(self, email: str) -> tuple[str, dict[str, Any]] | None:
        for account_id, data in self._registry.iter_records(TABLE):
            if data is not None and data["email"] == email:
                return account_id, data
        return None

    # --- data created before accounts ---------------------------------------------

    def _adopt_legacy_data(self, folder: Path, account_key: bytes) -> bool:
        """Move the pre-accounts database (device key) into the first account (its key)."""
        legacy = self.data_dir / LEGACY_DATABASE
        if not has_encrypted_data(legacy):
            return False
        target = folder / ACCOUNT_DATABASE
        shutil.copy2(legacy, target)
        new_cipher = RecordCipher(account_key)
        copy = EncryptedDatabase(target, self._device_cipher)
        try:
            copy.rekey(new_cipher)
        finally:
            copy.close()
        legacy_photos = self.data_dir / PHOTOS_DIR
        if legacy_photos.is_dir():
            (folder / PHOTOS_DIR).mkdir(exist_ok=True)
            for file in legacy_photos.glob("*.enc"):
                location = f"photos:{file.stem}".encode()
                try:
                    data = self._device_cipher.decrypt(file.read_bytes(), location)
                except DecryptionError:
                    continue
                (folder / PHOTOS_DIR / file.name).write_bytes(new_cipher.encrypt(data, location))
        return True

    def _remove_legacy_data(self) -> None:
        for name in (LEGACY_DATABASE, LEGACY_DATABASE + "-journal", LEGACY_DATABASE + "-wal"):
            (self.data_dir / name).unlink(missing_ok=True)
        shutil.rmtree(self.data_dir / PHOTOS_DIR, ignore_errors=True)


def open_registry(path: Path, device_cipher: RecordCipher) -> EncryptedDatabase:
    return EncryptedDatabase(path, device_cipher, ACCOUNTS_SCHEMA)
