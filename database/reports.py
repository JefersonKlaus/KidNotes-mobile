"""Repository for generated reports (one per student and period).

The text is the AI draft, already with the child's real name put back, and is
editable by the teacher before exporting the PDF. Stored encrypted like all
other records.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any

from database.connection import EncryptedDatabase

TABLE = "reports"
TEXT_MAX_LENGTH = 20000


class ReportNotFoundError(LookupError):
    """The report does not exist."""


class ReportRepository:
    def __init__(self, database: EncryptedDatabase) -> None:
        self._db = database

    def add(
        self,
        class_id: str,
        student_id: str,
        period_start: date,
        period_end: date,
        text: str,
        event_count: int,
        model: str,
    ) -> dict[str, Any]:
        report_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "class_id": class_id,
            "student_id": student_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "text": text[:TEXT_MAX_LENGTH],
            "event_count": event_count,
            "model": model,
            "created_at": now,
            "updated_at": now,
        }
        self._db.insert(TABLE, report_id, data)
        return self._to_report(report_id, data)

    def update_text(self, report_id: str, text: str) -> dict[str, Any]:
        data = self._db.get(TABLE, report_id)
        if data is None:
            raise ReportNotFoundError(report_id)
        data.update(text=text[:TEXT_MAX_LENGTH], updated_at=datetime.now(timezone.utc).isoformat())
        self._db.update(TABLE, report_id, data)
        return self._to_report(report_id, data)

    def get(self, report_id: str) -> dict[str, Any] | None:
        data = self._db.get(TABLE, report_id)
        return None if data is None else self._to_report(report_id, data)

    def list_for_class(self, class_id: str) -> list[dict[str, Any]]:
        """Reports of a class, newest first."""
        reports = [
            self._to_report(report_id, data)
            for report_id, data in self._db.iter_records(TABLE)
            if data is not None and data["class_id"] == class_id
        ]
        return sorted(reports, key=lambda r: r["created_at"], reverse=True)

    @staticmethod
    def _to_report(report_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": report_id,
            "class_id": data["class_id"],
            "student_id": data["student_id"],
            "period_start": date.fromisoformat(data["period_start"]),
            "period_end": date.fromisoformat(data["period_end"]),
            "text": data["text"],
            "event_count": data["event_count"],
            "model": data["model"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }
