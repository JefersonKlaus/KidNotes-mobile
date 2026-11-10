"""Photos for the report PDF, in pure Python (no Pillow: no native code on phones).

- JPEG (camera, and the phone gallery, which gives JPEG): embedded as is, a PDF
  viewer decodes it (DCTDecode). The EXIF orientation is read so a photo taken
  with the phone sideways is drawn upright.
- PNG: the compressed pixels go into the PDF almost as they are (the PNG
  "predictors" are PDF ones too); with transparency, the pixels are decoded
  here and the alpha becomes a soft mask (drawn over the white page).
- WebP, GIF, HEIC, interlaced or 16-bit transparent PNG: not supported
  (`pdf_compatible` is False); the photo picker shows them greyed out.
"""

import struct
import zlib
from dataclasses import dataclass

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# JPEG "start of frame" markers (they hold the size); C4, C8 and CC are not frames.
_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}  # color type -> samples per pixel


class ImageError(ValueError):
    """The bytes are not an image this module can put in a PDF."""


@dataclass(eq=False)  # compared by identity (the data can be megabytes)
class PdfImage:
    """An image XObject: its dictionary entries and its (compressed) data."""

    width: int  # stored pixels
    height: int
    color_space: bytes  # e.g. b"/DeviceRGB" or b"[/Indexed /DeviceRGB 3 <...>]"
    bits: int
    filter: bytes  # b"/DCTDecode" or b"/FlateDecode"
    data: bytes
    decode_parms: bytes = b""
    decode: bytes = b""  # e.g. inverted CMYK of Adobe JPEGs
    smask: "PdfImage | None" = None  # transparency
    orientation: int = 1  # EXIF orientation (1 = upright)

    @property
    def display_size(self) -> tuple[int, int]:
        """(width, height) as the photo is seen (orientations 5-8 turn it by 90°)."""
        if self.orientation in (5, 6, 7, 8):
            return self.height, self.width
        return self.width, self.height


# Maps the image's unit square to the displayed box, for each EXIF orientation:
# X = a1*u + b1*v + c1, Y = a2*u + b2*v + c2 (u, v: stored image; X, Y: display).
_ORIENTATION = {
    1: (1, 0, 0, 0, 1, 0),
    2: (-1, 0, 1, 0, 1, 0),  # mirrored
    3: (-1, 0, 1, 0, -1, 1),  # upside down
    4: (1, 0, 0, 0, -1, 1),  # mirrored vertically
    5: (0, -1, 1, -1, 0, 1),  # transposed
    6: (0, 1, 0, -1, 0, 1),  # turned 90° (phone held upright)
    7: (0, 1, 0, 1, 0, 0),  # transversed
    8: (0, -1, 1, 1, 0, 0),  # turned 270°
}


def placement_matrix(
    orientation: int, x: float, y: float, width: float, height: float
) -> tuple[float, ...]:
    """PDF `cm` matrix drawing the image upright in the box (x, y, width, height)."""
    a1, b1, c1, a2, b2, c2 = _ORIENTATION.get(orientation, _ORIENTATION[1])
    return (width * a1, height * a2, width * b1, height * b2, x + width * c1, y + height * c2)


def pdf_compatible(data: bytes) -> bool:
    """Quick check (headers only): can this photo go into the PDF?"""
    try:
        if data.startswith(b"\xff\xd8"):
            _jpeg_info(data)
            return True
        if data.startswith(_PNG_SIGNATURE):
            header = _png_chunks(data)[0]
            return _png_supported(header)
    except (ImageError, struct.error, IndexError, ValueError):
        return False
    return False


def pdf_image(data: bytes) -> PdfImage:
    """The photo as a PDF image. Raises ImageError if it can't be used."""
    try:
        if data.startswith(b"\xff\xd8"):
            return _jpeg(data)
        if data.startswith(_PNG_SIGNATURE):
            return _png(data)
    except (struct.error, IndexError, zlib.error) as error:
        raise ImageError(f"damaged image: {error}") from error
    raise ImageError("only JPEG and PNG photos can go into the PDF")


# --- JPEG -------------------------------------------------------------------------------


def _jpeg_info(data: bytes) -> tuple[int, int, int, int, bool]:
    """(width, height, components, orientation, adobe) from the JPEG markers."""
    position, orientation, adobe = 2, 1, False
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            raise ImageError("damaged JPEG")
        marker = data[position + 1]
        if marker == 0xFF:  # padding
            position += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            position += 2
            continue
        (length,) = struct.unpack(">H", data[position + 2 : position + 4])
        segment = data[position + 4 : position + 2 + length]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            orientation = _exif_orientation(segment[6:])
        elif marker == 0xEE and segment.startswith(b"Adobe"):
            adobe = True
        elif marker in _SOF_MARKERS:
            bits, height, width, components = struct.unpack(">BHHB", segment[:6])
            if bits != 8 or width == 0 or height == 0 or components not in (1, 3, 4):
                raise ImageError("unsupported JPEG")
            return width, height, components, orientation, adobe
        elif marker == 0xDA:  # image data before any frame header
            break
        position += 2 + length
    raise ImageError("JPEG without a frame header")


def _exif_orientation(tiff: bytes) -> int:
    """Orientation tag (0x0112) of the first EXIF directory; 1 if absent."""
    try:
        order = {b"II": "<", b"MM": ">"}[tiff[:2]]
        (offset,) = struct.unpack(order + "I", tiff[4:8])
        (count,) = struct.unpack(order + "H", tiff[offset : offset + 2])
        for index in range(count):
            entry = tiff[offset + 2 + 12 * index : offset + 14 + 12 * index]
            tag, _kind, _n, value = struct.unpack(order + "HHIH", entry[:10])
            if tag == 0x0112:
                return value if value in _ORIENTATION else 1
    except (KeyError, struct.error):
        pass
    return 1


def _jpeg(data: bytes) -> PdfImage:
    width, height, components, orientation, adobe = _jpeg_info(data)
    color_space = {1: b"/DeviceGray", 3: b"/DeviceRGB", 4: b"/DeviceCMYK"}[components]
    # Adobe's CMYK JPEGs are stored inverted.
    decode = b"[1 0 1 0 1 0 1 0]" if components == 4 and adobe else b""
    return PdfImage(width, height, color_space, 8, b"/DCTDecode", data,
                    decode=decode, orientation=orientation)


# --- PNG --------------------------------------------------------------------------------


def _png_chunks(data: bytes) -> tuple[tuple[int, ...], bytes, bytes, bytes]:
    """(IHDR fields, PLTE, tRNS, IDAT joined)."""
    position = len(_PNG_SIGNATURE)
    header: tuple[int, ...] | None = None
    palette = transparency = b""
    idat = bytearray()
    while position + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        body = data[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            transparency = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        position += 12 + length
    if header is None or not idat:
        raise ImageError("damaged PNG")
    return header, palette, transparency, bytes(idat)


def _png_supported(header: tuple[int, ...]) -> bool:
    width, height, depth, color_type, _compression, _filter, interlace = header
    if interlace or width == 0 or height == 0 or color_type not in _PNG_CHANNELS:
        return False
    if color_type in (4, 6):  # with alpha: decoded here, 8 bits only
        return depth == 8
    return depth in ((1, 2, 4, 8) if color_type == 3 else (8, 16))


def _png(data: bytes) -> PdfImage:
    header, palette, _transparency, idat = _png_chunks(data)
    if not _png_supported(header):
        raise ImageError("unsupported PNG (interlaced or unusual format)")
    width, height, depth, color_type = header[:4]
    channels = _PNG_CHANNELS[color_type]
    if color_type in (0, 2, 3):
        # The PNG data goes in as is: same zlib stream, same row filters.
        colors = 1 if color_type in (0, 3) else 3
        if color_type == 3:
            if not palette:
                raise ImageError("PNG palette missing")
            color_space = b"[/Indexed /DeviceRGB %d <%s>]" % (
                len(palette) // 3 - 1, palette.hex().encode()
            )
        else:
            color_space = b"/DeviceGray" if color_type == 0 else b"/DeviceRGB"
        parms = b"<< /Predictor 15 /Colors %d /BitsPerComponent %d /Columns %d >>" % (
            colors, depth, width
        )
        return PdfImage(width, height, color_space, depth, b"/FlateDecode", idat, parms)
    # Gray+alpha or RGBA (8 bits): decode, then split the colors from the alpha.
    pixels = _unfilter(zlib.decompress(idat), width, height, channels)
    color_channels = channels - 1
    color = bytearray(width * height * color_channels)
    for channel in range(color_channels):
        color[channel::color_channels] = pixels[channel::channels]
    alpha = pixels[channels - 1 :: channels]
    mask = PdfImage(width, height, b"/DeviceGray", 8, b"/FlateDecode", zlib.compress(alpha))
    color_space = b"/DeviceGray" if color_channels == 1 else b"/DeviceRGB"
    return PdfImage(width, height, color_space, 8, b"/FlateDecode",
                    zlib.compress(bytes(color)), smask=mask)


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    """Undo the PNG row filters (8-bit samples, `bpp` bytes per pixel)."""
    stride = width * bpp
    if len(raw) < (stride + 1) * height:
        raise ImageError("damaged PNG data")
    out = bytearray(stride * height)
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        kind = raw[start]
        line = bytearray(raw[start + 1 : start + 1 + stride])
        if kind == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:  # Up
            line = bytearray((a + b) & 0xFF for a, b in zip(line, previous, strict=True))
        elif kind == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:  # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = previous[i]
                corner = previous[i - bpp] if i >= bpp else 0
                estimate = left + up - corner
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else corner
                line[i] = (line[i] + predictor) & 0xFF
        elif kind != 0:
            raise ImageError("damaged PNG filter")
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return bytes(out)
