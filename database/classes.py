"""Repository for school classes stored in the encrypted database."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from database.connection import EncryptedDatabase
from theme import CLASS_COLORS

logger = logging.getLogger(__name__)

TABLE = "classes"
NAME_MAX_LENGTH = 60
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ClassValidationError(ValueError):
    """Invalid class data. `code` identifies the problem (for UI messages)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ClassRepository:
    def __init__(self, database: EncryptedDatabase) -> None:
        self._db = database

    def add(self, name: str, color: str = CLASS_COLORS[0]) -> dict[str, Any]:
        name = " ".join(name.split())  # trim and collapse inner spaces
        if not name:
            raise ClassValidationError("name_required")
        if len(name) > NAME_MAX_LENGTH:
            raise ClassValidationError("name_too_long")
        if not _HEX_COLOR.match(color):
            raise ClassValidationError("invalid_color")

        class_id = uuid.uuid4().hex
        data = {
            "name": name,
            "color": color,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._db.insert(TABLE, class_id, data)
        return self._to_class(class_id, data)

    def get(self, class_id: str) -> dict[str, Any] | None:
        data = self._db.get(TABLE, class_id)
        return None if data is None else self._to_class(class_id, data)

    def list_all(self) -> list[dict[str, Any]]:
        """All classes in creation order. Records that can't be decrypted are skipped."""
        classes = []
        for class_id, data in self._db.iter_records(TABLE):
            if data is None:
                logger.warning("Skipping class %s: it could not be decrypted.", class_id)
                continue
            classes.append(self._to_class(class_id, data))
        return classes

    @staticmethod
    def _to_class(class_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": class_id,
            "name": data["name"],
            "color": data["color"],
            "created_at": data["created_at"],
        }
