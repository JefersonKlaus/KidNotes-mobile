"""Camera screen: live preview and a shutter button.

Offered on every platform; where no camera can be started (e.g. a desktop
without camera support), the screen says so and the teacher can use the gallery.

The photo comes back as bytes and goes straight into the event draft (memory);
it is only written to disk encrypted when the event is saved.
"""

import asyncio
import logging
from typing import Any

import flet as ft
import flet_camera as fc

from components import safe_update
from i18n import Translator
from media import purge_plaintext_media_cache

logger = logging.getLogger(__name__)

# The first start shows the OS camera permission prompt: give the teacher time.
INITIALIZE_TIMEOUT = 60
CALL_TIMEOUT = 15


def default_camera_factory() -> Any:
    return fc.Camera(expand=True, preview_enabled=True)


class CameraScreen:
    scrollable = False  # the preview fills the screen

    def __init__(
        self,
        tr: Translator,
        on_photo: Any,
        on_close: Any,
        camera_factory: Any = default_camera_factory,
    ) -> None:
        self.tr = tr
        self.on_photo = on_photo
        self.on_close = on_close
        self.camera = camera_factory()
        self.ready = False
        self.status = ft.Text(self.tr.t("camera.starting"), color=ft.Colors.WHITE, size=14)
        self.shutter = ft.IconButton(
            icon=ft.Icons.CAMERA,
            icon_size=44,
            icon_color=ft.Colors.WHITE,
            tooltip=self.tr.t("camera.capture"),
            disabled=True,
            on_click=self.capture,
        )

    def build(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(content=self.camera, expand=True),
                    ft.Container(content=self.status, padding=ft.Padding(left=20, right=20)),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_color=ft.Colors.WHITE,
                                tooltip=self.tr.t("camera.close"),
                                on_click=lambda _: self.on_close(),
                            ),
                            self.shutter,
                            ft.Container(width=48),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=8,
                expand=True,
            ),
            bgcolor=ft.Colors.BLACK,
            padding=ft.Padding(bottom=16),
            expand=True,
        )

    async def start(self) -> None:
        """Open the back camera. Called by the app after the screen is on the page."""
        try:
            cameras = await asyncio.wait_for(self.camera.get_available_cameras(), CALL_TIMEOUT)
            if not cameras:
                raise RuntimeError("No camera found.")
            camera = next(
                (c for c in cameras if c.lens_direction == fc.CameraLensDirection.BACK),
                cameras[0],
            )
            await asyncio.wait_for(
                self.camera.initialize(
                    camera, fc.ResolutionPreset.VERY_HIGH, enable_audio=False
                ),
                INITIALIZE_TIMEOUT,
            )
        except Exception:
            logger.exception("The camera could not be started.")
            self._set_status(self.tr.t("camera.unavailable"))
            return
        self.ready = True
        self.shutter.disabled = False
        safe_update(self.shutter)
        self._set_status("")

    async def capture(self, _: Any = None) -> None:
        if not self.ready:
            return
        self.shutter.disabled = True
        safe_update(self.shutter)
        try:
            data = await asyncio.wait_for(self.camera.take_picture(), CALL_TIMEOUT)
            if not data:
                raise RuntimeError("Empty photo.")
        except Exception:
            logger.exception("The photo could not be taken.")
            self._set_status(self.tr.t("camera.capture_failed"))
            self.shutter.disabled = False
            safe_update(self.shutter)
            return
        finally:
            purge_plaintext_media_cache()
        self.on_photo(bytes(data))

    def _set_status(self, text: str) -> None:
        self.status.value = text
        self.status.visible = bool(text)
        safe_update(self.status)
