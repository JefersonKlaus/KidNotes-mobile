"""Images in the reports: choosing event photos, storing them, and the PDF."""

import asyncio
import io
import re
import struct
import zlib
from datetime import date, timedelta

import flet as ft
import pytest

from database.reports import MAX_REPORT_PHOTOS, ReportNotFoundError
from i18n import Translator
from reports.document import build_report_pdf
from reports.images import ImageError, pdf_compatible, pdf_image
from reports.pdf import MARGIN
from tests.conftest import (
    collect_texts,
    find_all,
    find_button,
    notice_is_error,
    notice_text,
    screen_text,
)
from tests.test_app import by_name, layout
from tests.test_reports import FakeExporter, generate, open_reports, pdf_text, report_chips

TODAY = date.today()
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32  # accepted by the app, not by the PDF


def tiny_jpeg(width=20, height=10) -> bytes:
    """A JPEG header the app and the PDF writer accept (no Pillow needed)."""
    frame = struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8\xff\xc0" + frame + b"\xff\xd9"


# --- images: formats --------------------------------------------------------------------

def encode(image, fmt, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def test_pillow_needed_only_by_the_tests():
    import reports.images

    source = open(reports.images.__file__, encoding="utf-8").read()
    assert "PIL" not in source and "import PIL" not in source


def marked_picture(mode="RGB"):
    """200x100: red left half, blue right half, green square in the top-left corner."""
    image_module = pytest.importorskip("PIL.Image")  # only for making test images
    red, blue, green = (255, 0, 0), (0, 0, 255), (0, 200, 0)
    if mode == "RGBA":
        red, blue, green = (*red, 255), (*blue, 255), (*green, 255)
    picture = image_module.new(mode, (200, 100), red)
    picture.paste(blue, (100, 0, 200, 100))
    picture.paste(green, (0, 0, 40, 20))
    return picture


def render(pdf: bytes):
    pdfium = pytest.importorskip("pypdfium2")
    return pdfium.PdfDocument(pdf)[0].render(scale=2).to_pil().convert("RGB")


def photo_box(page):
    """Bounding box of the saturated pixels (the photo; the text is grey)."""
    pixels, (width, height) = page.load(), page.size
    xs, ys = [], []
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            r, g, b = pixels[x, y]
            if max(r, g, b) - min(r, g, b) > 120:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def color_name(rgb):
    r, g, b = rgb
    if r > 180 and g < 90 and b < 90:
        return "red"
    if b > 180 and r < 90:
        return "blue"
    if g > 140 and r < 90 and b < 90:
        return "green"
    return str(rgb)


def pdf_with(photos, text="Texto."):
    student = {"name": "Clara Souza", "birth_date": None}
    report = {"period_start": date(2025, 2, 1), "period_end": date(2025, 6, 30), "text": text}
    return build_report_pdf(Translator("pt"), student, "Turma", report, photos=photos)


def assert_upright(data):
    page = render(pdf_with([(data, "02/05/2025")]))
    x0, y0, x1, y1 = photo_box(page)
    width, height = x1 - x0, y1 - y0
    assert width > height * 1.7  # landscape, 2:1
    assert color_name(page.getpixel((x0 + width // 20, y0 + height // 20))) == "green"
    assert color_name(page.getpixel((x0 + width // 4, y0 + height * 3 // 4))) == "red"
    assert color_name(page.getpixel((x0 + width * 3 // 4, y0 + height // 2))) == "blue"


@pytest.mark.parametrize("orientation", range(1, 9))
def test_phone_photos_are_upright_in_the_pdf(orientation):
    """Phones store some photos turned/mirrored, with an EXIF "orientation" tag."""
    image_module = pytest.importorskip("PIL.Image")  # only for making test images
    ops = image_module.Transpose
    # How to turn the stored pixels to the upright picture, per EXIF orientation:
    to_upright = {1: None, 2: ops.FLIP_LEFT_RIGHT, 3: ops.ROTATE_180,
                  4: ops.FLIP_TOP_BOTTOM, 5: ops.TRANSPOSE, 6: ops.ROTATE_270,
                  7: ops.TRANSVERSE, 8: ops.ROTATE_90}[orientation]
    undo = {ops.ROTATE_270: ops.ROTATE_90, ops.ROTATE_90: ops.ROTATE_270}
    upright = marked_picture()
    stored = upright if to_upright is None else upright.transpose(undo.get(to_upright, to_upright))
    exif = image_module.Exif()
    exif[0x0112] = orientation
    data = encode(stored, "JPEG", quality=95, exif=exif.tobytes())

    assert pdf_image(data).orientation == orientation
    assert_upright(data)


@pytest.mark.parametrize(
    "variant", ["jpeg", "jpeg_progressive", "png_rgb", "png_rgba", "png_palette"]
)
def test_image_formats_in_the_pdf(variant):
    picture = marked_picture("RGBA" if variant == "png_rgba" else "RGB")
    data = {
        "jpeg": lambda: encode(picture, "JPEG", quality=95),
        "jpeg_progressive": lambda: encode(picture, "JPEG", quality=95, progressive=True),
        "png_rgb": lambda: encode(picture, "PNG"),
        "png_rgba": lambda: encode(picture, "PNG"),
        "png_palette": lambda: encode(picture.convert("P"), "PNG"),
    }[variant]()
    assert pdf_compatible(data)
    assert_upright(data)


@pytest.mark.parametrize("mode", ["L", "LA"])
def test_gray_images_render(mode):
    data = encode(marked_picture().convert(mode), "PNG")
    assert pdf_compatible(data)
    render(pdf_with([(data, "")]))  # no error


def test_transparent_parts_are_white_on_the_page():
    image_module = pytest.importorskip("PIL.Image")  # only for making test images
    picture = image_module.new("RGBA", (100, 100), (255, 0, 0, 255))
    picture.paste((0, 0, 255, 0), (50, 0, 100, 100))  # right half: fully transparent blue
    page = render(pdf_with([(encode(picture, "PNG"), "")]))
    x0, y0, x1, y1 = photo_box(page)  # only the red half is visible
    right = page.getpixel((x1 + (x1 - x0) // 2, (y0 + y1) // 2))
    assert color_name(page.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))) == "red"
    assert min(right) > 240  # white page, not blue


def png(width, height, color_type, rows, depth=8, interlace=0, palette=b""):
    """A PNG built by hand: each row is (filter type, raw bytes already filtered)."""
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    raw = b"".join(bytes([kind]) + data for kind, data in rows)
    plte = chunk(b"PLTE", palette) if palette else b""
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + plte
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def paeth(left, up, corner):
    estimate = left + up - corner
    pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
    return left if pa <= pb and pa <= pc else up if pb <= pc else corner


def test_every_png_row_filter_is_decoded():
    """RGBA PNG whose rows use the 5 filter types (None, Sub, Up, Average, Paeth)."""
    width, height, bpp = 4, 5, 4
    pixels = [bytes((17 * (x + 3 * y) + c * 40) & 0xFF for x in range(width) for c in range(bpp))
              for y in range(height)]
    rows, previous = [], bytes(width * bpp)
    for kind, line in enumerate(pixels):
        out = bytearray()
        for i, value in enumerate(line):
            left = line[i - bpp] if i >= bpp else 0
            up = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            predictor = [0, left, up, (left + up) >> 1, paeth(left, up, corner)][kind]
            out.append((value - predictor) & 0xFF)
        rows.append((kind, bytes(out)))
        previous = line

    image = pdf_image(png(width, height, 6, rows))

    decoded_rgb = zlib.decompress(image.data)
    decoded_alpha = zlib.decompress(image.smask.data)
    flat = b"".join(pixels)
    assert decoded_rgb == bytes(b for i, b in enumerate(flat) if i % 4 != 3)
    assert decoded_alpha == flat[3::4]


def test_simple_pngs_go_in_without_decoding():
    rows = [(0, bytes([10, 20, 30] * 2))] * 2
    image = pdf_image(png(2, 2, 2, rows))
    assert image.filter == b"/FlateDecode" and b"/Predictor 15" in image.decode_parms
    assert image.smask is None
    palette = pdf_image(png(2, 1, 3, [(0, bytes([0, 1]))], palette=bytes(range(6))))
    assert palette.color_space.startswith(b"[/Indexed /DeviceRGB 1 <")


@pytest.mark.parametrize(
    "data",
    [
        WEBP,
        b"GIF89a" + b"\x00" * 20,
        png(2, 2, 2, [(0, bytes(6))] * 2, interlace=1),  # interlaced
        png(2, 2, 6, [(0, bytes(16))] * 2, depth=16),  # 16-bit with transparency
        b"\xff\xd8\xff\xe0" + b"\x00" * 40,  # JPEG without a frame header
        b"not an image",
    ],
)
def test_formats_the_pdf_cannot_hold(data):
    assert not pdf_compatible(data)
    with pytest.raises(ImageError):
        pdf_image(data)


def test_a_damaged_photo_is_left_out_and_the_pdf_still_works(caplog):
    pdf = pdf_with([(WEBP, "01/03/2025"), (tiny_jpeg(), "02/05/2025")])
    assert pdf.count(b"/Subtype /Image") == 1
    assert "A photo was left out of the PDF" in caplog.text


# --- the PDF layout ----------------------------------------------------------------------


def image_placements(pdf: bytes) -> list[list[tuple[float, float, float, float]]]:
    """Per page: (x, y, width, height) of each drawn image (orientation 1)."""
    pages = []
    for stream in re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.DOTALL):
        try:
            content = zlib.decompress(stream)
        except zlib.error:
            continue
        if b" Do Q" not in content and b"BT" not in content:
            continue  # an image, not a page
        found = re.findall(rb"q ([\d.-]+) [\d.-]+ [\d.-]+ ([\d.-]+) ([\d.-]+) ([\d.-]+) cm /Im",
                           content)
        pages.append([(float(e), float(f), float(a), float(d)) for a, d, e, f in found])
    return pages


def test_photos_two_per_row_with_captions_after_the_text():
    photos = [(tiny_jpeg(), f"0{i}/05/2025") for i in range(1, 4)]
    pdf = pdf_with(photos)
    text = pdf_text(pdf)

    assert text.index("Texto.") < text.index("Registros fotográficos") < text.index("Professor(a)")
    assert all(caption in text for _, caption in photos)
    [placements] = [p for p in image_placements(pdf) if p]
    (x1, y1, *_), (x2, y2, *_), (x3, y3, *_) = placements
    assert y1 == y2 and x1 < x2  # first row: side by side
    assert y3 < y1  # second row below


def test_many_photos_continue_on_new_pages_inside_the_margins():
    pdf = pdf_with([(tiny_jpeg(200, 300), "01/05/2025")] * MAX_REPORT_PHOTOS,
                   text="Parágrafo.\n\n" * 20)
    pages = [p for p in image_placements(pdf) if p]
    assert len(pages) >= 2 and sum(len(p) for p in pages) == MAX_REPORT_PHOTOS
    for placements in pages:
        for x, y, width, height in placements:
            assert y >= MARGIN + 20 - 0.5  # above the footer
            assert y + height <= 841.89 - MARGIN + 0.5
            assert x >= MARGIN - 0.5 and x + width <= 595.28 - MARGIN + 0.5


def test_no_photo_section_without_photos():
    assert "Registros fotográficos" not in pdf_text(pdf_with([]))


# --- storage -----------------------------------------------------------------------------


def saved_report(repositories, sample_class):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    return repositories.reports.add(sample_class["id"], alice["id"], TODAY - timedelta(days=30),
                                    TODAY, "Texto.", 1, "m")


def test_report_photos_are_stored_in_order(repositories, sample_class, database):
    report = saved_report(repositories, sample_class)
    assert report["photo_ids"] == []

    repositories.reports.set_photos(report["id"], ["b" * 32, "a" * 32])
    assert repositories.reports.get(report["id"])["photo_ids"] == ["b" * 32, "a" * 32]

    with pytest.raises(ValueError):
        repositories.reports.set_photos(report["id"], ["a" * 32, "a" * 32])  # duplicated
    with pytest.raises(ValueError):
        repositories.reports.set_photos(report["id"], [f"{i:032x}" for i in range(13)])
    with pytest.raises(ReportNotFoundError):
        repositories.reports.set_photos("missing", [])


def test_reports_made_before_photos_existed(repositories, sample_class, database):
    report = saved_report(repositories, sample_class)
    data = database.get("reports", report["id"])
    del data["photo_ids"]
    database.update("reports", report["id"], data)
    assert repositories.reports.get(report["id"])["photo_ids"] == []


# --- screens -----------------------------------------------------------------------------


def add_photo_events(repositories, sample_class):
    """Alice: two events with photos in the period, one without photos, one too old."""
    cid = sample_class["id"]
    alice = by_name(repositories, cid, "Alice Martins")
    bento = by_name(repositories, cid, "Bento Oliveira")
    events = repositories.events
    newer = events.add(cid, [alice["id"]], "Alice pintou.", TODAY - timedelta(days=2),
                       [tiny_jpeg(), WEBP])
    older = events.add(cid, [alice["id"], bento["id"]], "Alice e Bento na areia.",
                       TODAY - timedelta(days=10), [tiny_jpeg(), tiny_jpeg()])
    events.add(cid, [alice["id"]], "Sem foto.", TODAY - timedelta(days=5))
    events.add(cid, [alice["id"]], "Muito antiga.", TODAY - timedelta(days=400), [tiny_jpeg()])
    return older, newer


def open_review(page, repositories, sample_class, exporter=None, language="en"):
    older, newer = add_photo_events(repositories, sample_class)
    app = open_reports(page, repositories, sample_class, exporter=exporter, language=language)
    report_chips(page)["Alice Martins (3)"].on_select(None)
    generate(page)
    find_button(page.controls[-1], "Open" if language == "en" else "Abrir").on_click(None)
    return app, older, newer


def photo_tiles(page):
    return {c.data.split(":")[1]: c for c in find_all(
        page.controls[-1], lambda c: isinstance(c, ft.Container) and str(c.data).startswith(
            "photo:"))}


def insert_button(page):
    return layout(page)[1].content.controls[0]


def test_add_images_opens_the_event_photos_of_the_period(make_page, repositories,
                                                         sample_class):
    page = make_page()
    app, older, newer = open_review(page, repositories, sample_class)
    assert "Images in the report (0)" in screen_text(page)

    find_button(page.controls[-1], "Add images").on_click(None)

    assert app.route == "report_photos"
    text = screen_text(page)
    assert "Choose images" in text and "Alice Martins" in text
    # Events with photos of the report's period, oldest first (no "Muito antiga").
    assert text.index("Alice e Bento na areia.") < text.index("Alice pintou.")
    assert "Muito antiga." not in text and "Sem foto." not in text
    tiles = photo_tiles(page)
    assert list(tiles) == [*older["photo_ids"], newer["photo_ids"][0]]
    # The WebP photo is shown greyed out and can't be chosen.
    [greyed] = find_all(page.controls[-1], lambda c: str(getattr(c, "data", "")).startswith(
        "unsupported:"))
    assert "Not supported in the PDF" in collect_texts(greyed) and greyed.on_click is None
    assert insert_button(page).content == "Insert images (0)"


def test_choose_many_images_and_insert_them(make_page, repositories, sample_class):
    page = make_page()
    app, older, newer = open_review(page, repositories, sample_class)
    find_button(page.controls[-1], "Add images").on_click(None)
    tiles = photo_tiles(page)

    tiles[newer["photo_ids"][0]].on_click(None)  # chosen in any order...
    tiles[older["photo_ids"][1]].on_click(None)
    tiles[older["photo_ids"][0]].on_click(None)
    tiles[older["photo_ids"][0]].on_click(None)  # ...and a second tap unselects
    assert tiles[older["photo_ids"][1]].border.top.width == 3  # highlighted
    assert insert_button(page).content == "Insert images (2)"

    insert_button(page).on_click(None)

    report = repositories.reports.get(app.review_report_id)
    assert report["photo_ids"] == [older["photo_ids"][1], newer["photo_ids"][0]]  # by date
    assert app.route == "report_review"
    assert "Images in the report (2)" in screen_text(page)
    assert notice_text(page) == "2 images in the report."


def test_back_from_the_picker_changes_nothing(make_page, repositories, sample_class):
    page = make_page()
    app, older, _ = open_review(page, repositories, sample_class)
    find_button(page.controls[-1], "Add images").on_click(None)
    photo_tiles(page)[older["photo_ids"][0]].on_click(None)

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)

    assert app.route == "report_review"
    assert repositories.reports.get(app.review_report_id)["photo_ids"] == []


def test_unsaved_text_survives_the_trip_to_the_picker(make_page, repositories, sample_class):
    from types import SimpleNamespace

    page = make_page()
    app, older, _ = open_review(page, repositories, sample_class)
    area = find_all(layout(page)[0], lambda c: isinstance(c, ft.TextField))[0]
    area.value = "Texto ainda não salvo."
    area.on_change(SimpleNamespace(control=area))

    find_button(page.controls[-1], "Add images").on_click(None)
    photo_tiles(page)[older["photo_ids"][0]].on_click(None)
    insert_button(page).on_click(None)

    area = find_all(layout(page)[0], lambda c: isinstance(c, ft.TextField))[0]
    assert area.value == "Texto ainda não salvo."


def test_limit_of_images_per_report(make_page, repositories, sample_class, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "MAX_REPORT_PHOTOS", 1)
    page = make_page()
    _, older, _ = open_review(page, repositories, sample_class)
    find_button(page.controls[-1], "Add images").on_click(None)
    tiles = photo_tiles(page)

    tiles[older["photo_ids"][0]].on_click(None)
    tiles[older["photo_ids"][1]].on_click(None)

    assert notice_is_error(page) and notice_text(page) == "Up to 1 images per report."
    assert insert_button(page).content == "Insert images (1)"


def test_remove_an_image_from_the_report(make_page, repositories, sample_class):
    page = make_page()
    app, older, newer = open_review(page, repositories, sample_class)
    repositories.reports.set_photos(app.review_report_id,
                                    [older["photo_ids"][0], newer["photo_ids"][0]])
    app.render()
    body = layout(page)[0]
    [remove, _] = find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
                           and str(c.data).startswith("remove-photo:"))
    assert remove.tooltip == "Remove image"

    remove.on_click(None)

    assert repositories.reports.get(app.review_report_id)["photo_ids"] == [newer["photo_ids"][0]]
    assert notice_text(page) == "Image removed from the report."
    assert layout(page)[0] is body  # the page didn't jump to the top


def test_generated_pdf_has_the_chosen_images(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    app, older, newer = open_review(page, repositories, sample_class, exporter)
    repositories.reports.set_photos(app.review_report_id,
                                    [older["photo_ids"][0], newer["photo_ids"][0]])
    app.render()

    generate_pdf = layout(page)[1].content.controls[1]
    assert find_button(generate_pdf, "Generate PDF") is generate_pdf
    asyncio.run(generate_pdf.on_click(None))

    [(kind, data, _)] = exporter.calls
    text = pdf_text(data)
    assert data.count(b"/Subtype /Image") == 2
    assert "Photo records" in text
    assert Translator("en").format_date(older["occurred_on"]) in text  # captions: event dates


def test_an_image_deleted_from_its_event(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    app, older, newer = open_review(page, repositories, sample_class, exporter)
    repositories.reports.set_photos(app.review_report_id,
                                    [older["photo_ids"][0], newer["photo_ids"][0]])
    # The teacher removes that photo from the event: its file is deleted.
    repositories.events.update(older["id"], older["student_ids"], older["description"],
                               older["occurred_on"], [older["photo_ids"][1]])
    app.render()

    assert "Image not available" in screen_text(page)  # shown, and can be removed
    asyncio.run(layout(page)[1].content.controls[1].on_click(None))
    [(_, data, _)] = exporter.calls
    assert data.count(b"/Subtype /Image") == 1  # the PDF still works


def test_empty_state_when_the_period_has_no_photos(make_page, repositories, sample_class):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.events.add(sample_class["id"], [alice["id"]], "Só texto.",
                            TODAY - timedelta(days=1))
    page = make_page()
    open_reports(page, repositories, sample_class)
    report_chips(page)["Alice Martins (1)"].on_select(None)
    generate(page)
    find_button(page.controls[-1], "Open").on_click(None)

    find_button(page.controls[-1], "Add images").on_click(None)

    assert "No photos in this period" in screen_text(page)


def test_images_in_portuguese(make_page, repositories, sample_class):
    page = make_page()
    _, older, _ = open_review(page, repositories, sample_class, language="pt")
    assert "Imagens do relatório (0)" in screen_text(page)
    find_button(page.controls[-1], "Adicionar imagens").on_click(None)
    assert "Escolher imagens" in screen_text(page)
    assert "Formato não aceito no PDF" in screen_text(page)
    photo_tiles(page)[older["photo_ids"][0]].on_click(None)
    assert insert_button(page).content == "Inserir imagens (1)"
    insert_button(page).on_click(None)
    assert notice_text(page) == "1 imagem no relatório."
