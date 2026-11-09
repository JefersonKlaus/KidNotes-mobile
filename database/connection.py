"""SQLite connection where every record is stored encrypted.

What is stored in plain text: table names, random record ids and the insertion
order. Everything else (names, colors, dates...) lives inside the encrypted
`payload` column. See `crypto.py` for the encryption format.
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from database.crypto import DecryptionError, RecordCipher

KEY_CHECK_NAME = "key_check"
KEY_CHECK_VALUE = b"kidnotes-key-check-v1"

# Each entry upgrades the schema by one version (PRAGMA user_version).
# Never edit an entry that was already released; append a new one instead.
MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE meta (
        name  TEXT PRIMARY KEY,
        value BLOB NOT NULL          -- encrypted
    );
    CREATE TABLE classes (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,  -- insertion order only
        id      TEXT NOT NULL UNIQUE,               -- random UUID
        payload BLOB NOT NULL                       -- encrypted JSON
    );
    """,
    # v2: students (the class they belong to is inside the encrypted payload)
    # and app settings (e.g. the last opened class).
    """
    CREATE TABLE students (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,
        id      TEXT NOT NULL UNIQUE,
        payload BLOB NOT NULL
    );
    CREATE TABLE settings (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,
        id      TEXT NOT NULL UNIQUE,               -- setting name
        payload BLOB NOT NULL
    );
    """,
    # v3: significant events of the children's learning stories. The class,
    # the linked students and the photo ids are inside the encrypted payload;
    # the photos themselves are encrypted files (see photos.py).
    """
    CREATE TABLE events (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,
        id      TEXT NOT NULL UNIQUE,
        payload BLOB NOT NULL
    );
    """,
    # v4: generated reports (one per student and period; the text is editable).
    """
    CREATE TABLE reports (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,
        id      TEXT NOT NULL UNIQUE,
        payload BLOB NOT NULL
    );
    """,
]


# Tables that hold encrypted records (used to validate table names).
RECORD_TABLES = frozenset({"classes", "students", "settings", "events", "reports"})

# The account registry (accounts.db) has its own, much smaller schema.
ACCOUNTS_MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE meta (
        name  TEXT PRIMARY KEY,
        value BLOB NOT NULL          -- encrypted
    );
    CREATE TABLE accounts (
        seq     INTEGER PRIMARY KEY AUTOINCREMENT,
        id      TEXT NOT NULL UNIQUE,               -- random UUID
        payload BLOB NOT NULL                       -- encrypted: email, wrapped key...
    );
    """,
]


@dataclass(frozen=True)
class Schema:
    migrations: list[str]
    record_tables: frozenset[str]


def app_schema() -> Schema:
    """Schema of a teacher's data (classes, students, events...)."""
    return Schema(MIGRATIONS, RECORD_TABLES)


ACCOUNTS_SCHEMA = Schema(ACCOUNTS_MIGRATIONS, frozenset({"accounts"}))


class DatabaseKeyError(Exception):
    """The database exists but cannot be decrypted with the available key."""


def has_encrypted_data(path: Path) -> bool:
    """True if `path` is a database already initialized with some encryption key."""
    if not path.exists():
        return False
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
        ).fetchone()
        if row is None:
            return False
        return (
            connection.execute("SELECT 1 FROM meta WHERE name = ?", (KEY_CHECK_NAME,)).fetchone()
            is not None
        )
    finally:
        connection.close()


class EncryptedDatabase:
    def __init__(
        self, path: Path | str, cipher: RecordCipher, schema: Schema | None = None
    ) -> None:
        self.path = Path(path)
        self._cipher = cipher
        self.schema = schema or app_schema()
        # Flet runs sync event handlers in worker threads: share one connection
        # and serialize access with a lock.
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._migrate()
            self._verify_key()
        except Exception:
            self._connection.close()
            raise

    # --- lifecycle -----------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            migrations = self.schema.migrations
            for number, script in enumerate(migrations[version:], start=version + 1):
                # executescript() commits first, so the version bump is part of
                # the same script to keep each migration atomic.
                self._connection.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;"
                )

    def _verify_key(self) -> None:
        """Make sure the key matches the one used to create the database."""
        aad = self._aad("meta", KEY_CHECK_NAME)
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM meta WHERE name = ?", (KEY_CHECK_NAME,)
            ).fetchone()
            if row is None:
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO meta (name, value) VALUES (?, ?)",
                        (KEY_CHECK_NAME, self._cipher.encrypt(KEY_CHECK_VALUE, aad)),
                    )
                return
        try:
            ok = self._cipher.decrypt(row[0], aad) == KEY_CHECK_VALUE
        except DecryptionError:
            ok = False
        if not ok:
            raise DatabaseKeyError("The database cannot be decrypted with the current key.")

    # --- encrypted blobs (files kept outside SQLite, e.g. photos) -------

    def encrypt_blob(self, data: bytes, location: str) -> bytes:
        """Encrypt `data` with the database key, bound to `location` (e.g. `photos:<id>`)."""
        return self._cipher.encrypt(data, location.encode())

    def decrypt_blob(self, blob: bytes, location: str) -> bytes:
        """Raises `DecryptionError` if the blob is not the one saved for `location`."""
        return self._cipher.decrypt(blob, location.encode())

    # --- encrypted records ---------------------------------------------

    @staticmethod
    def _aad(table: str, record_id: str) -> bytes:
        return f"{table}:{record_id}".encode()

    def _check_table(self, table: str) -> None:
        if table not in self.schema.record_tables:
            raise ValueError(f"Unknown table: {table}")

    def rekey(self, new_cipher: RecordCipher) -> None:
        """Re-encrypt every record (and the key check) with a new key, in one transaction.

        Records that can't be decrypted with the current key are left as they are.
        Files encrypted with `encrypt_blob` (photos) must be re-encrypted by the caller.
        """
        with self._lock, self._connection:
            tables = [("meta", "name", "value")] + [
                (table, "id", "payload") for table in sorted(self.schema.record_tables)
            ]
            for table, key_column, value_column in tables:
                rows = self._connection.execute(
                    f"SELECT {key_column}, {value_column} FROM {table}"
                ).fetchall()
                for record_id, blob in rows:
                    aad = self._aad(table, record_id)
                    try:
                        plaintext = self._cipher.decrypt(blob, aad)
                    except DecryptionError:
                        continue
                    self._connection.execute(
                        f"UPDATE {table} SET {value_column} = ? WHERE {key_column} = ?",
                        (new_cipher.encrypt(plaintext, aad), record_id),
                    )
            self._cipher = new_cipher

    def insert(self, table: str, record_id: str, data: dict[str, Any]) -> None:
        self._check_table(table)
        payload = self._encrypt_record(table, record_id, data)
        with self._lock, self._connection:
            self._connection.execute(
                f"INSERT INTO {table} (id, payload) VALUES (?, ?)", (record_id, payload)
            )

    def update(self, table: str, record_id: str, data: dict[str, Any]) -> None:
        """Replace the data of an existing record (re-encrypted with a new nonce)."""
        self._check_table(table)
        payload = self._encrypt_record(table, record_id, data)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"UPDATE {table} SET payload = ? WHERE id = ?", (payload, record_id)
            )
        if cursor.rowcount == 0:
            raise KeyError(record_id)

    def put(self, table: str, record_id: str, data: dict[str, Any]) -> None:
        """Insert the record, or replace it if it already exists."""
        self._check_table(table)
        payload = self._encrypt_record(table, record_id, data)
        with self._lock, self._connection:
            self._connection.execute(
                f"INSERT INTO {table} (id, payload) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (record_id, payload),
            )

    def get(self, table: str, record_id: str) -> dict[str, Any] | None:
        """The record's data, or None if it doesn't exist or can't be decrypted."""
        self._check_table(table)
        with self._lock:
            row = self._connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
        return None if row is None else self._decrypt_record(table, record_id, row[0])

    def _encrypt_record(self, table: str, record_id: str, data: dict[str, Any]) -> bytes:
        return self._cipher.encrypt(
            json.dumps(data, ensure_ascii=False).encode(), self._aad(table, record_id)
        )

    def _decrypt_record(self, table: str, record_id: str, payload: bytes) -> dict[str, Any] | None:
        try:
            return json.loads(self._cipher.decrypt(payload, self._aad(table, record_id)))
        except (DecryptionError, ValueError):
            return None

    def iter_records(self, table: str) -> Iterator[tuple[str, dict[str, Any] | None]]:
        """Yield `(id, data)` in insertion order; `data` is None if it can't be decrypted."""
        self._check_table(table)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id, payload FROM {table} ORDER BY seq"
            ).fetchall()
        for record_id, payload in rows:
            yield record_id, self._decrypt_record(table, record_id, payload)
