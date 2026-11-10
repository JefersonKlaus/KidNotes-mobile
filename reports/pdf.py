"""Minimal PDF writer for the reports (pure Python, no dependencies).

Why not a PDF library: fpdf2/reportlab need Pillow (native code), an extra
binary package for Android/iOS. A report is text and a few photos, so this
small writer is enough: A4 pages, standard Helvetica fonts (WinAnsi encoding:
all Portuguese accents), word wrap with the real font metrics, automatic page
breaks, a "Page X of Y" footer, and JPEG/PNG photos (see `reports/images.py`).
"""

import unicodedata
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reports.font_metrics import HELVETICA, HELVETICA_BOLD
from reports.images import PdfImage, placement_matrix

PAGE_WIDTH = 595.28  # A4, in points
PAGE_HEIGHT = 841.89
MARGIN = 56.0  # ~2 cm
FOOTER_Y = 30.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

INK = (0.21, 0.25, 0.32)
MUTED = (0.47, 0.51, 0.59)
PRIMARY = (0.42, 0.55, 0.90)


def to_winansi(text: str) -> bytes:
    """Encode text for the standard fonts; characters outside cp1252 are simplified."""
    out = bytearray()
    for char in unicodedata.normalize("NFC", text):
        try:
            out += char.encode("cp1252")
        except UnicodeEncodeError:
            # e.g. "ł" -> "l"; characters with no plain form (emoji) are dropped.
            out += unicodedata.normalize("NFKD", char).encode("ascii", "ignore")
    return bytes(out)


def text_width(text: str, size: float, bold: bool = False) -> float:
    widths = HELVETICA_BOLD if bold else HELVETICA
    return sum(widths[b] for b in to_winansi(text)) * size / 1000


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    """Split a paragraph into lines that fit `width` (long words are split)."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if text_width(candidate, size, bold) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while text_width(word, size, bold) > width:  # a single very long word
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, bold) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def _escape(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _pdf_text_string(text: str) -> bytes:
    """Unicode string for metadata (UTF-16BE with BOM, as a hex string)."""
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"


@dataclass
class PdfDocument:
    title: str = ""
    footer: str = ""  # left part of the footer; "{page}" / "{pages}" are filled in
    pages: list[list[bytes]] = field(default_factory=list)
    y: float = 0.0
    images: list[PdfImage] = field(default_factory=list)  # /Im1, /Im2...

    def __post_init__(self) -> None:
        self.new_page()

    # --- layout ---------------------------------------------------------------------

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_HEIGHT - MARGIN

    def _ensure_space(self, height: float) -> None:
        if self.y - height < MARGIN + 20:  # keep clear of the footer
            self.new_page()

    def ensure_space(self, height: float) -> None:
        """Start a new page unless `height` points still fit on this one."""
        self._ensure_space(height)

    def draw_text(self, x: float, y: float, text: str, size: float = 9,
                  bold: bool = False, color=MUTED) -> None:
        """One line of text at (x, y) (no wrapping), e.g. a photo caption."""
        self._draw(x, y, text, size, bold, color)

    def draw_image(self, image: PdfImage, x: float, y: float, width: float,
                   height: float) -> None:
        """The image upright in the box whose bottom-left corner is (x, y)."""
        if image not in self.images:  # identity (PdfImage has eq=False)
            self.images.append(image)
        name = b"/Im%d" % (self.images.index(image) + 1)
        matrix = placement_matrix(image.orientation, x, y, width, height)
        self.pages[-1].append(
            b"q %.4f %.4f %.4f %.4f %.2f %.2f cm %s Do Q" % (*matrix, name)
        )

    def _draw(self, x: float, y: float, text: str, size: float, bold: bool, color) -> None:
        font = b"/F2" if bold else b"/F1"
        r, g, b = color
        self.pages[-1].append(
            b"BT %.3f %.3f %.3f rg %s %.1f Tf %.2f %.2f Td (%s) Tj ET"
            % (r, g, b, font, size, x, y, _escape(to_winansi(text)))
        )

    def text(
        self,
        text: str,
        size: float = 11,
        bold: bool = False,
        color=INK,
        leading: float | None = None,
        space_after: float = 0,
        keep_with_next: float = 0,
    ) -> None:
        """A paragraph, wrapped to the page width; continues on a new page if needed.

        `keep_with_next`: room (points) that must fit after it on the same page,
        so a title is never left alone at the bottom of a page.
        """
        leading = leading or size * 1.45
        lines = wrap(text, size, CONTENT_WIDTH, bold) or [""]
        if keep_with_next:
            self._ensure_space(leading * len(lines) + space_after + keep_with_next)
        for line in lines:
            self._ensure_space(leading)
            self.y -= leading
            self._draw(MARGIN, self.y, line, size, bold, color)
        self.y -= space_after

    def spacer(self, height: float) -> None:
        self.y -= height

    def rule(self, color=PRIMARY, space: float = 10) -> None:
        self._ensure_space(space * 2)
        self.y -= space
        r, g, b = color
        self.pages[-1].append(
            b"%.3f %.3f %.3f RG 0.8 w %.2f %.2f m %.2f %.2f l S"
            % (r, g, b, MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        )
        self.y -= space

    def signature(self, label: str) -> None:
        """A line to sign, with a label under it (kept on one page)."""
        self._ensure_space(70)
        self.y -= 50
        r, g, b = INK
        self.pages[-1].append(
            b"%.3f %.3f %.3f RG 0.6 w %.2f %.2f m %.2f %.2f l S"
            % (r, g, b, MARGIN, self.y, MARGIN + 220, self.y)
        )
        self.y -= 14
        self._draw(MARGIN, self.y, label, 10, False, MUTED)

    # --- output ------------------------------------------------------------------------

    def render(self) -> bytes:
        total = len(self.pages)
        objects: list[bytes] = []  # object n is objects[n - 1]

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        catalog = add(b"")  # filled in below
        pages_obj = add(b"")
        font_regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        font_bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )
        xobjects = []
        for number, image in enumerate(self.images, start=1):
            xobjects.append(b"/Im%d %d 0 R" % (number, add(_image_object(image, add))))
        resources = add(
            b"<< /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << %s >> >>"
            % (font_regular, font_bold, b" ".join(xobjects))
        )
        page_ids = []
        for number, commands in enumerate(self.pages, start=1):
            footer = self.footer.format(page=number, pages=total)
            footer_cmd = b"BT %.3f %.3f %.3f rg /F1 8.0 Tf %.2f %.2f Td (%s) Tj ET" % (
                *MUTED, MARGIN, FOOTER_Y, _escape(to_winansi(footer))
            )
            stream = zlib.compress(b"\n".join([*commands, footer_cmd]))
            content = add(
                b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
                + stream
                + b"\nendstream"
            )
            page_ids.append(
                add(
                    b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                    b"/Resources %d 0 R /Contents %d 0 R >>"
                    % (pages_obj, PAGE_WIDTH, PAGE_HEIGHT, resources, content)
                )
            )
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
        objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % p for p in page_ids),
            total,
        )
        created = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ").encode()
        info = add(
            b"<< /Title %s /Producer (RelatorioFacil Infantil) /CreationDate (%s) >>"
            % (_pdf_text_string(self.title), created)
        )

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for offset in offsets:
            out += b"%010d 00000 n \n" % offset
        out += (
            b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog, info, xref)
        )
        return bytes(out)


def _image_object(image: PdfImage, add) -> bytes:
    """The image XObject (its soft mask, if any, is added as another object)."""
    entries = [
        b"/Type /XObject /Subtype /Image /Width %d /Height %d" % (image.width, image.height),
        b"/ColorSpace " + image.color_space,
        b"/BitsPerComponent %d" % image.bits,
        b"/Filter " + image.filter,
        b"/Length %d" % len(image.data),
    ]
    if image.decode_parms:
        entries.append(b"/DecodeParms " + image.decode_parms)
    if image.decode:
        entries.append(b"/Decode " + image.decode)
    if image.smask is not None:
        entries.append(b"/SMask %d 0 R" % add(_image_object(image.smask, add)))
    return b"<< " + b" ".join(entries) + b" >>\nstream\n" + image.data + b"\nendstream"

