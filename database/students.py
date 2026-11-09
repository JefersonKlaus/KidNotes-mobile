"""Repository for students stored in the encrypted database.

Students are never deleted: "removing" a student from a class deactivates it
(`active = False`), so its history is kept. The class screen lists them as
"transferred", and they can be reactivated.
"""

import logging
import unicodedata
import uuid
from datetime import date, datetime, timezone
from typing import Any

from database.connection import EncryptedDatabase
from theme import AVATAR_COLORS

logger = logging.getLogger(__name__)

TABLE = "students"
NAME_MAX_LENGTH = 80
NOTES_MAX_LENGTH = 4000  # "extra information": free text about the child
MIN_BIRTH_DATE = date(1900, 1, 1)


class StudentValidationError(ValueError):
    """Invalid student data. `code` identifies the problem (for UI messages)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StudentNotFoundError(LookupError):
    """The student (or the class it would be added to) does not exist."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise StudentValidationError("name_required")
    if len(name) > NAME_MAX_LENGTH:
        raise StudentValidationError("name_too_long")
    return name


def _check_birth_date(birth_date: date | None, today: date | None = None) -> None:
    if birth_date is None:
        return
    if isinstance(birth_date, datetime) or not isinstance(birth_date, date):
        raise StudentValidationError("invalid_birth_date")
    if birth_date > (today or date.today()):
        raise StudentValidationError("birth_date_in_future")
    if birth_date < MIN_BIRTH_DATE:
        raise StudentValidationError("invalid_birth_date")


def initials(name: str) -> str:
    words = name.split()
    if not words:
        return "?"
    letters = words[0][0] + (words[-1][0] if len(words) > 1 else "")
    return letters.upper()


def _sort_key(name: str) -> str:
    # Accent-insensitive alphabetical order ("Álvaro" next to "Alice").
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class StudentRepository:
    def __init__(self, database: EncryptedDatabase) -> None:
        self._db = database

    def add(self, class_id: str, name: str, birth_date: date | None = None) -> dict[str, Any]:
        name = _clean_name(name)
        _check_birth_date(birth_date)
        if self._db.get("classes", class_id) is None:
            raise StudentNotFoundError(f"Class not found: {class_id}")

        student_id = uuid.uuid4().hex
        now = _now()
        data = {
            "class_id": class_id,
            "name": name,
            "birth_date": birth_date.isoformat() if birth_date else None,
            "active": True,
            "created_at": now,
            "updated_at": now,
            "deactivated_at": None,
        }
        self._db.insert(TABLE, student_id, data)
        return self._to_student(student_id, data)

    def update_notes(self, student_id: str, notes: str) -> dict[str, Any]:
        """Save the child's extra information (free text, no date): likes, habits..."""
        notes = notes.strip()
        if len(notes) > NOTES_MAX_LENGTH:
            raise StudentValidationError("notes_too_long")
        data = self._load(student_id)
        data.update(notes=notes, updated_at=_now())
        self._db.update(TABLE, student_id, data)
        return self._to_student(student_id, data)

    def update(self, student_id: str, name: str, birth_date: date | None) -> dict[str, Any]:
        name = _clean_name(name)
        _check_birth_date(birth_date)
        data = self._load(student_id)
        data.update(
            name=name,
            birth_date=birth_date.isoformat() if birth_date else None,
            updated_at=_now(),
        )
        self._db.update(TABLE, student_id, data)
        return self._to_student(student_id, data)

    def deactivate(self, student_id: str) -> dict[str, Any]:
        """Remove the student from its class, keeping the record."""
        data = self._load(student_id)
        if data["active"]:
            now = _now()
            data.update(active=False, deactivated_at=now, updated_at=now)
            self._db.update(TABLE, student_id, data)
        return self._to_student(student_id, data)

    def reactivate(self, student_id: str) -> dict[str, Any]:
        """Bring a removed (transferred) student back to its class."""
        data = self._load(student_id)
        if not data["active"]:
            data.update(active=True, deactivated_at=None, updated_at=_now())
            self._db.update(TABLE, student_id, data)
        return self._to_student(student_id, data)

    def get(self, student_id: str) -> dict[str, Any] | None:
        data = self._db.get(TABLE, student_id)
        return None if data is None else self._to_student(student_id, data)

    def list_active(self, class_id: str) -> list[dict[str, Any]]:
        """Active students of a class, in alphabetical order."""
        students = [s for s in self._all() if s["class_id"] == class_id and s["active"]]
        return sorted(students, key=lambda s: _sort_key(s["name"]))

    def list_inactive(self, class_id: str) -> list[dict[str, Any]]:
        """Removed (transferred) students of a class, in alphabetical order."""
        students = [s for s in self._all() if s["class_id"] == class_id and not s["active"]]
        return sorted(students, key=lambda s: _sort_key(s["name"]))

    def count_active_by_class(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for student in self._all():
            if student["active"]:
                counts[student["class_id"]] = counts.get(student["class_id"], 0) + 1
        return counts

    def _all(self) -> list[dict[str, Any]]:
        students = []
        for student_id, data in self._db.iter_records(TABLE):
            if data is None:
                logger.warning("Skipping student %s: it could not be decrypted.", student_id)
                continue
            students.append(self._to_student(student_id, data))
        return students

    def _load(self, student_id: str) -> dict[str, Any]:
        data = self._db.get(TABLE, student_id)
        if data is None:
            raise StudentNotFoundError(f"Student not found: {student_id}")
        return data

    @staticmethod
    def _to_student(student_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": student_id,
            "class_id": data["class_id"],
            "name": data["name"],
            "birth_date": date.fromisoformat(data["birth_date"]) if data["birth_date"] else None,
            "active": data["active"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "deactivated_at": data["deactivated_at"],
            # Extra information (stored inside the encrypted payload; older
            # records don't have it yet).
            "notes": data.get("notes", ""),
            # Display helpers (not stored).
            "initials": initials(data["name"]),
            "color": AVATAR_COLORS[int(student_id[:8], 16) % len(AVATAR_COLORS)],
        }
