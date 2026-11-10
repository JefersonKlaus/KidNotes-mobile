"""App settings stored in the encrypted database."""

from database.connection import EncryptedDatabase

TABLE = "settings"
LAST_CLASS = "last_class"  # before "default_class" existed: read once as the default
DEFAULT_CLASS = "default_class"
GROQ_API_KEY = "groq_api_key"
REPORT_INSTRUCTIONS = "report_instructions"
REPORT_INSTRUCTIONS_MAX_LENGTH = 2000


class AppSettings:
    def __init__(self, database: EncryptedDatabase) -> None:
        self._db = database

    def get_default_class_id(self) -> str | None:
        """The principal class: the app opens on it (the "last class" of older versions)."""
        data = self._db.get(TABLE, DEFAULT_CLASS)
        if data and data.get("class_id"):
            return data["class_id"]
        return self.get_last_class_id()

    def set_default_class_id(self, class_id: str) -> None:
        self._db.put(TABLE, DEFAULT_CLASS, {"class_id": class_id})

    def get_last_class_id(self) -> str | None:
        """The class the teacher opened last (the app starts on it)."""
        data = self._db.get(TABLE, LAST_CLASS)
        return data.get("class_id") if data else None

    def set_last_class_id(self, class_id: str | None) -> None:
        self._db.put(TABLE, LAST_CLASS, {"class_id": class_id})

    def get_groq_api_key(self) -> str | None:
        """The teacher's Groq API key (used to write report drafts), if saved."""
        data = self._db.get(TABLE, GROQ_API_KEY)
        return (data or {}).get("key") or None

    def set_groq_api_key(self, key: str) -> None:
        self._db.put(TABLE, GROQ_API_KEY, {"key": key.strip()})

    def clear_groq_api_key(self) -> None:
        """Forget the saved key (the record is deleted, not just emptied)."""
        self._db.delete(TABLE, GROQ_API_KEY)

    def get_report_instructions(self) -> str:
        """The teacher's instructions for the reports (structure, standards...), or ""."""
        data = self._db.get(TABLE, REPORT_INSTRUCTIONS)
        return (data or {}).get("text") or ""

    def set_report_instructions(self, text: str) -> None:
        text = text.strip()[:REPORT_INSTRUCTIONS_MAX_LENGTH]
        self._db.put(TABLE, REPORT_INSTRUCTIONS, {"text": text})
