"""Local encrypted storage (SQLite + AES-256-GCM).

Public API:
- `open_account_store()`: opens the account registry at startup.
- `AccountStore.register()` / `.login()`: returns a `Session` with the
  teacher's own encrypted database.
- `Repositories.from_database(session.database)`: classes, students, events
  and settings of that teacher.
- `DatabaseKeyError`: the data exists but cannot be decrypted.
"""

from database.accounts import AccountError, AccountStore, Session
from database.bootstrap import open_account_store
from database.classes import ClassRepository, ClassValidationError
from database.connection import DatabaseKeyError, EncryptedDatabase
from database.events import EventNotFoundError, EventRepository, EventValidationError
from database.repositories import Repositories
from database.settings import AppSettings
from database.students import StudentNotFoundError, StudentRepository, StudentValidationError

__all__ = [
    "AccountError",
    "AccountStore",
    "AppSettings",
    "ClassRepository",
    "ClassValidationError",
    "DatabaseKeyError",
    "EncryptedDatabase",
    "EventNotFoundError",
    "EventRepository",
    "EventValidationError",
    "Repositories",
    "Session",
    "StudentNotFoundError",
    "StudentRepository",
    "StudentValidationError",
    "open_account_store",
]
