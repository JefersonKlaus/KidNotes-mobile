"""Startup: data folder + device encryption key + account registry."""

import os
from pathlib import Path

from database.accounts import LEGACY_DATABASE, AccountStore, open_registry
from database.connection import DatabaseKeyError, has_encrypted_data
from database.crypto import RecordCipher, decode_key, encode_key, generate_key
from database.keys import KeyStore, create_key_store

REGISTRY_FILE = "accounts.db"
DATABASE_FILE = LEGACY_DATABASE  # kept for data created before accounts existed


def app_data_dir() -> Path:
    """App private data folder.

    `FLET_APP_STORAGE_DATA` is set by Flet both in packaged apps (the app's
    private storage on the phone) and by `flet run` (`.flet/storage/data`).
    """
    env_dir = os.environ.get("FLET_APP_STORAGE_DATA")
    if env_dir:
        path = Path(env_dir)
    else:  # e.g. `python main.py`: same folder `flet run` uses
        path = Path(__file__).resolve().parent.parent / ".flet" / "storage" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def load_or_create_key(key_store: KeyStore, *database_paths: Path) -> bytes:
    encoded = await key_store.get()
    if encoded:
        try:
            return decode_key(encoded)
        except ValueError as error:
            raise DatabaseKeyError("The stored encryption key is invalid.") from error

    if any(has_encrypted_data(path) for path in database_paths):
        # Never create a new key over existing data: it would be unreadable.
        raise DatabaseKeyError("The encryption key of the existing database was not found.")

    key = generate_key()
    await key_store.set(encode_key(key))
    if await key_store.get() != encode_key(key):
        raise DatabaseKeyError("The encryption key could not be saved.")
    return key


async def open_account_store(
    data_dir: Path | None = None, key_store: KeyStore | None = None
) -> AccountStore:
    """Open the account registry with the device key (created on the first start)."""
    data_dir = data_dir or app_data_dir()
    registry_path = data_dir / REGISTRY_FILE
    key_store = key_store or create_key_store(data_dir)
    key = await load_or_create_key(key_store, registry_path, data_dir / LEGACY_DATABASE)
    device_cipher = RecordCipher(key)
    return AccountStore(open_registry(registry_path, device_cipher), data_dir, device_cipher)
