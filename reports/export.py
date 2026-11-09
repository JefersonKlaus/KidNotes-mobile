"""Getting the PDF out of the app: save it (file dialog) or share it (share sheet).

The PDF goes from memory straight to the place the teacher chooses; the app
doesn't keep an unencrypted copy.
"""

import flet as ft

PDF_MIME = "application/pdf"


class ReportExporter:
    """Create it inside the Flet session, so the services register with the page."""

    def __init__(self) -> None:
        self._picker = ft.FilePicker()
        self._share = ft.Share()

    async def save(self, data: bytes, filename: str) -> bool:
        """System "save as" dialog (Android/iOS/desktop) or download (web)."""
        path = await self._picker.save_file(
            file_name=filename,
            src_bytes=data,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
        )
        return path is not None

    async def share(self, data: bytes, filename: str) -> None:
        """System share sheet: WhatsApp, e-mail, Drive..."""
        await self._share.share_files(
            [ft.ShareFile.from_bytes(data, mime_type=PDF_MIME, name=filename)]
        )
