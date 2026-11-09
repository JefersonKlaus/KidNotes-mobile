"""Repository for significant events: the moments that tell each child's learning story.

An event belongs to a class and is linked to one or more of its students. It
has a description, the date it happened and optional photos. A student's
story is the list of events they are linked to, newest first.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from database.connection import EncryptedDatabase
from database.photos import PhotoError, PhotoStore

logger = logging.getLogger(__name__)

TABLE = "events"
DESCRIPTION_MAX_LENGTH = 2000
MAX_PHOTOS_PER_EVENT = 10
MIN_EVENT_DATE = date(2000, 1, 1)


class EventValidationError(ValueError):
    """Invalid event data. `code` identifies the problem (for UI messages)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EventNotFoundError(LookupError):
    """The event does not exist."""


class EventRepository:
    def __init__(self, database: EncryptedDatabase, photos: PhotoStore) -> None:
        self._db = database
        self._photos = photos

    def add(
        self,
        class_id: str,
        student_ids: list[str] | set[str],
        description: str,
        occurred_on: date,
        photos: list[bytes] | None = None,
    ) -> dict[str, Any]:
        photos = photos or []
        description = description.strip()
        student_ids = sorted(set(student_ids))
        self._validate(class_id, student_ids, description, occurred_on, photos, len(photos))

        photo_ids: list[str] = []
        try:
            for photo in photos:
                photo_ids.append(self._photos.save(photo))
            event_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            data = {
                "class_id": class_id,
                "student_ids": student_ids,
                "description": description,
                "occurred_on": occurred_on.isoformat(),
                "photo_ids": photo_ids,
                "created_at": now,
                "updated_at": now,
            }
            self._db.insert(TABLE, event_id, data)
        except Exception:
            for photo_id in photo_ids:  # don't leave orphan photo files behind
                self._photos.delete(photo_id)
            raise
        return self._to_event(event_id, data)

    def update(
        self,
        event_id: str,
        student_ids: list[str] | set[str],
        description: str,
        occurred_on: date,
        photos: list[str | bytes],
    ) -> dict[str, Any]:
        """Edit an event. `photos`: ids of photos to keep and bytes of new ones, in order."""
        data = self._db.get(TABLE, event_id)
        if data is None:
            raise EventNotFoundError(event_id)
        description = description.strip()
        student_ids = sorted(set(student_ids))
        if any(isinstance(p, str) and p not in data["photo_ids"] for p in photos):
            raise EventValidationError("invalid_photo")
        new_photos = [p for p in photos if isinstance(p, bytes)]
        self._validate(
            data["class_id"],
            student_ids,
            description,
            occurred_on,
            new_photos,
            len(photos),
            already_linked=set(data["student_ids"]),
        )

        added: list[str] = []
        try:
            photo_ids = []
            for photo in photos:
                if isinstance(photo, bytes):
                    photo = self._photos.save(photo)
                    added.append(photo)
                photo_ids.append(photo)
            removed = [p for p in data["photo_ids"] if p not in photo_ids]
            data.update(
                student_ids=student_ids,
                description=description,
                occurred_on=occurred_on.isoformat(),
                photo_ids=photo_ids,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self._db.update(TABLE, event_id, data)
        except Exception:
            for photo_id in added:
                self._photos.delete(photo_id)
            raise
        for photo_id in removed:  # only once the event no longer uses them
            self._photos.delete(photo_id)
        return self._to_event(event_id, data)

    def get(self, event_id: str) -> dict[str, Any] | None:
        data = self._db.get(TABLE, event_id)
        return None if data is None else self._to_event(event_id, data)

    def _validate(
        self,
        class_id: str,
        student_ids: list[str],
        description: str,
        occurred_on: date,
        new_photos: list[bytes],
        photo_count: int,
        already_linked: set[str] | None = None,
    ) -> None:
        already_linked = already_linked or set()
        if not student_ids:
            raise EventValidationError("no_students")
        for student_id in student_ids:
            student = self._db.get("students", student_id)
            if not student or student["class_id"] != class_id:
                raise EventValidationError("unknown_student")
            # A child removed from the class can stay linked to an event they
            # were already in, but can't be added to events any more.
            if not student["active"] and student_id not in already_linked:
                raise EventValidationError("unknown_student")
        if not description and not photo_count:
            raise EventValidationError("empty")
        if len(description) > DESCRIPTION_MAX_LENGTH:
            raise EventValidationError("description_too_long")
        if isinstance(occurred_on, datetime) or not isinstance(occurred_on, date):
            raise EventValidationError("invalid_date")
        if occurred_on > date.today():
            raise EventValidationError("date_in_future")
        if occurred_on < MIN_EVENT_DATE:
            raise EventValidationError("invalid_date")
        if photo_count > MAX_PHOTOS_PER_EVENT:
            raise EventValidationError("too_many_photos")
        for photo in new_photos:
            try:
                PhotoStore.validate(photo)
            except PhotoError as error:
                raise EventValidationError(error.code) from error

    def story(self, student_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Events linked to the student, newest first (by event date, then creation)."""
        events = [e for e in self._all() if student_id in e["student_ids"]]
        events.sort(key=lambda e: (e["occurred_on"], e["created_at"]), reverse=True)
        return events if limit is None else events[:limit]

    def count_by_student(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._all():
            for student_id in event["student_ids"]:
                counts[student_id] = counts.get(student_id, 0) + 1
        return counts

    def load_photo(self, photo_id: str) -> bytes | None:
        return self._photos.load(photo_id)

    def _all(self) -> list[dict[str, Any]]:
        events = []
        for event_id, data in self._db.iter_records(TABLE):
            if data is None:
                logger.warning("Skipping event %s: it could not be decrypted.", event_id)
                continue
            events.append(self._to_event(event_id, data))
        return events

    @staticmethod
    def _to_event(event_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event_id,
            "class_id": data["class_id"],
            "student_ids": list(data["student_ids"]),
            "description": data["description"],
            "occurred_on": date.fromisoformat(data["occurred_on"]),
            "photo_ids": list(data["photo_ids"]),
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }
