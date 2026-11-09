"""Where the database encryption key is kept.

- Packaged app (`flet build`): the OS secure storage, i.e. Android Keystore /
  iOS Keychain, through the `flet-secure-storage` extension. The key never
  touches the app's files.
- Development (`flet run`, tests): a key file next to the development
  database. Python runs on the computer in this mode and the secure storage
  extension is not available in the Flet client used by `flet run`.
"""

import os
from pathlib import Path
from typing import Protocol

import flet_secure_storage as fss
from flet.utils import is_embedded

KEY_NAME = "kidnotes.database_key.v1"


class KeyStore(Protocol):
    async def get(self) -> str | None: ...

    async def set(self, value: str) -> None: ...


class SecureKeyStore:
    """Android Keystore / iOS Keychain (only inside a packaged app)."""

    def __init__(self) -> None:
        # Created inside the Flet session, so it registers itself with the page.
        self._storage = fss.SecureStorage(
            # Readable after the first unlock since boot. The key only leaves
            # the device inside encrypted iOS backups, so restoring a backup on
            # a new iPhone keeps the database readable.
            ios_options=fss.IOSOptions(
                accessibility=fss.KeychainAccessibility.FIRST_UNLOCK,
            ),
        )

    async def get(self) -> str | None:
        return await self._storage.get(KEY_NAME)

    async def set(self, value: str) -> None:
        await self._storage.set(KEY_NAME, value)


class DevFileKeyStore:
    """Development only: the key is saved in a file readable only by the current user."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def get(self) -> str | None:
        return self.path.read_text(encoding="ascii").strip() if self.path.exists() else None

    async def set(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as file:
            file.write(value)


def create_key_store(data_dir: Path) -> KeyStore:
    if is_embedded():
        return SecureKeyStore()
    return DevFileKeyStore(data_dir / "dev-database.key")
