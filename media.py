"""Getting photos from the phone, without leaving unencrypted copies behind.

- Gallery: the system photo picker (`ft.FilePicker`). It needs no storage
  permission on Android.
- Camera: `flet-camera` (see `screens/camera.py`). The photo comes back as
  bytes.

Plugins may leave a plain copy of a picked or captured photo in the app's
own cache/temp folders. In a packaged app, those copies are deleted right
after the photo has been read (it is then only kept encrypted, see
`database/photos.py`). This is best effort: it only touches image files that
the photo plugins create, inside the app's private cache/temp folders. It
never runs in development, where the picked path is the developer's original
file.
"""

import logging
import os
from pathlib import Path

import flet as ft
from flet.utils import is_embedded

logger = logging.getLogger(__name__)

GALLERY_COMPRESSION_QUALITY = 80  # JPEG quality applied by the picker on phones
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif"}
PLUGIN_DIRS = ("file_picker", "image_picker")


def _app_scratch_dirs() -> list[Path]:
    dirs = [os.environ.get("FLET_APP_STORAGE_CACHE"), os.environ.get("FLET_APP_STORAGE_TEMP")]
    return [Path(d).resolve() for d in dirs if d]


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory)
        return True
    except ValueError:
        return False


def discard_plaintext_copy(path: str | None) -> None:
    """Delete a picker's temporary copy (only inside the app's cache/temp folders)."""
    if not path or not is_embedded():
        return
    file = Path(path)
    if any(_is_inside(file, d) for d in _app_scratch_dirs()):
        file.unlink(missing_ok=True)


def purge_plaintext_media_cache() -> int:
    """Delete photo copies left by the camera/picker plugins. Returns how many."""
    if not is_embedded():
        return 0
    removed = 0
    for root in _app_scratch_dirs():
        candidates = list(root.glob("CAP*"))  # camera plugin captures
        for plugin_dir in PLUGIN_DIRS:
            candidates += list((root / plugin_dir).rglob("*"))
        for file in candidates:
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
                try:
                    file.unlink()
                    removed += 1
                except OSError:
                    logger.warning("Could not delete cached photo %s", file)
    return removed


# Platforms where `flet-camera` works. It raises FletUnsupportedPlatformException
# ("Camera is currently only supported on Android, iOS and Web platforms.") when
# its control is shown anywhere else, e.g. in a desktop window (`flet run`).
CAMERA_PLATFORMS = (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)


def camera_supported(page: ft.Page) -> bool:
    """Same rule as `flet_camera.Camera`: Android, iOS or web."""
    return bool(getattr(page, "web", False)) or getattr(page, "platform", None) in CAMERA_PLATFORMS


class GalleryPicker:
    """Picks photos with the system picker. Create it inside the Flet session."""

    def __init__(self) -> None:
        self._picker = ft.FilePicker()

    async def pick_photos(self) -> list[bytes]:
        files = await self._picker.pick_files(
            file_type=ft.FilePickerFileType.IMAGE,
            allow_multiple=True,
            with_data=True,  # bytes also work when Python is not on the phone (`flet run`)
            compression_quality=GALLERY_COMPRESSION_QUALITY,
        )
        photos = []
        for file in files or []:
            if file.bytes:
                photos.append(file.bytes)
            discard_plaintext_copy(file.path)
        purge_plaintext_media_cache()
        return photos
