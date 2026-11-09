"""Encrypted photo files.

Photos are too large to keep inside SQLite rows, so each one is a separate
file in `<app data>/photos/<id>.enc`. The file content is AES-256-GCM
ciphertext (same key and format as the database records), bound to the photo
id: a file renamed or copied over another photo fails to decrypt.
Decrypted photos only exist in memory.
"""

import logging
import os
import re
import uuid
from pathlib import Path

from database.connection import EncryptedDatabase
from database.crypto import DecryptionError

logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 15 * 1024 * 1024
_PHOTO_ID = re.compile(r"^[0-9a-f]{32}$")


def image_type(data: bytes) -> str | None:
    """MIME type of a supported image, detected from its first bytes."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "image/heic"  # iPhone photos
    return None


class PhotoError(ValueError):
    """Invalid photo. `code`: `invalid_photo` or `photo_too_large`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PhotoStore:
    def __init__(self, directory: Path, database: EncryptedDatabase) -> None:
        self.directory = directory
        self._db = database
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate(data: bytes) -> None:
        if len(data) > MAX_PHOTO_BYTES:
            raise PhotoError("photo_too_large")
        if image_type(data) is None:
            raise PhotoError("invalid_photo")

    def save(self, data: bytes) -> str:
        """Encrypt and save a photo; returns its id."""
        self.validate(data)
        photo_id = uuid.uuid4().hex
        path = self._path(photo_id)
        temporary = path.with_suffix(".tmp")
        encrypted = self._db.encrypt_blob(data, f"photos:{photo_id}")
        with open(temporary, "wb") as file:
            file.write(encrypted)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)  # atomic: never a half-written photo
        return photo_id

    def load(self, photo_id: str) -> bytes | None:
        """The decrypted photo, or None if it is missing or can't be decrypted."""
        try:
            blob = self._path(photo_id).read_bytes()
            return self._db.decrypt_blob(blob, f"photos:{photo_id}")
        except (FileNotFoundError, DecryptionError, ValueError):
            logger.warning("Photo %s could not be loaded.", photo_id)
            return None

    def delete(self, photo_id: str) -> None:
        self._path(photo_id).unlink(missing_ok=True)

    def _path(self, photo_id: str) -> Path:
        if not _PHOTO_ID.match(photo_id):
            raise ValueError(f"Invalid photo id: {photo_id!r}")
        return self.directory / f"{photo_id}.enc"
