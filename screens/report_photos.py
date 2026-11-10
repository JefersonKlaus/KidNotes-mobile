"""Choose the photos of a report: all photos of the child's events in the
report's period, grouped by event (oldest first). Tap to select (many);
"Insert images" puts them in the report, in this order.

Photos the PDF can't hold (WebP, GIF, HEIC...) are shown greyed out and can't
be selected (see `reports/images.py`).
"""

from typing import Any

import flet as ft

from components import bottom_action_bar, empty_state, page_header, photo, safe_update
from i18n import Translator
from theme import COLORS

TILE_SIZE = 104


class ReportPhotosScreen:
    def __init__(
        self,
        student_name: str,
        period_start: str,
        period_end: str,
        groups: list[dict[str, Any]],
        selected: list[str],
        max_count: int,
        tr: Translator,
        on_confirm: Any,
        on_back: Any,
        on_limit: Any,
    ) -> None:
        """`groups`: [{"date", "description", "photos": [{"id", "data", "supported"}]}].

        `selected`: ids already chosen; the list is changed in place, so the
        choice survives a re-render of the screen.
        """
        self.student_name = student_name
        self.period_start = period_start
        self.period_end = period_end
        self.groups = groups
        self.selected = selected
        self.max_count = max_count
        self.tr = tr
        self.on_confirm = on_confirm
        self.on_back = on_back
        self.on_limit = on_limit
        self.tiles: dict[str, ft.Container] = {}
        self.insert_button: ft.FilledButton | None = None

    # --- layout -----------------------------------------------------------------------

    def build(self) -> ft.Column:
        self.tiles = {}
        if any(group["photos"] for group in self.groups):
            body: list[ft.Control] = [
                ft.Text(self.tr.t("report_photos.hint"), size=13, color=COLORS["muted"]),
                *[self._group(group) for group in self.groups if group["photos"]],
            ]
        else:
            body = [
                empty_state(
                    ft.Icons.PHOTO_LIBRARY_OUTLINED,
                    self.tr.t("report_photos.empty_title"),
                    self.tr.t("report_photos.empty_message", name=self.student_name,
                              start=self.period_start, end=self.period_end),
                )
            ]
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.tr.t("report_photos.title"),
                        f"{self.student_name} · {self.period_start} – {self.period_end}",
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(controls=body, spacing=16),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        bar = bottom_action_bar(self._insert_label(), ft.Icons.CHECK, lambda _: self.confirm())
        self.insert_button = bar.content.controls[0]
        return bar

    def _group(self, group: dict[str, Any]) -> ft.Column:
        header = [ft.Text(group["date"], size=14, weight=ft.FontWeight.W_700,
                          color=COLORS["ink"])]
        if group["description"]:
            header.append(ft.Text(group["description"], size=12, color=COLORS["muted"],
                                  max_lines=2, overflow=ft.TextOverflow.ELLIPSIS))
        tiles = [self._tile(item) for item in group["photos"]]
        return ft.Column(
            controls=[*header, ft.Row(controls=tiles, wrap=True, spacing=8, run_spacing=8)],
            spacing=6,
        )

    def _tile(self, item: dict[str, Any]) -> ft.Container:
        image = photo(item["data"], self.tr.t("report_review.photo_unavailable"),
                      width=TILE_SIZE, height=TILE_SIZE)
        if not item["supported"]:
            return ft.Container(
                content=ft.Stack(
                    controls=[
                        ft.Container(content=image, opacity=0.35),
                        ft.Container(
                            content=ft.Text(self.tr.t("report_photos.unsupported"), size=11,
                                            color=COLORS["ink"], text_align=ft.TextAlign.CENTER),
                            alignment=ft.Alignment.CENTER,
                            padding=6,
                            width=TILE_SIZE,
                            height=TILE_SIZE,
                        ),
                    ],
                ),
                width=TILE_SIZE,
                height=TILE_SIZE,
                border_radius=16,
                data=f"unsupported:{item['id']}",
            )
        tile = ft.Container(
            content=ft.Stack(
                controls=[
                    image,
                    ft.Container(  # the check mark, visible when selected
                        content=ft.Icon(ft.Icons.CHECK_CIRCLE, color=COLORS["primary"], size=26),
                        bgcolor=ft.Colors.WHITE,
                        border_radius=14,
                        top=6,
                        right=6,
                    ),
                ],
            ),
            width=TILE_SIZE,
            height=TILE_SIZE,
            border_radius=16,
            on_click=lambda _, pid=item["id"]: self.toggle(pid),
            data=f"photo:{item['id']}",
        )
        self.tiles[item["id"]] = tile
        self._style(tile, item["id"] in self.selected)
        return tile

    def _style(self, tile: ft.Container, selected: bool) -> None:
        tile.border = ft.Border.all(3 if selected else 1,
                                    COLORS["primary"] if selected else COLORS["border"])
        tile.content.controls[1].visible = selected

    def _insert_label(self) -> str:
        return self.tr.t("report_photos.insert", count=len(self.selected))

    # --- interactions -----------------------------------------------------------------

    def toggle(self, photo_id: str) -> None:
        if photo_id in self.selected:
            self.selected.remove(photo_id)
        elif len(self.selected) >= self.max_count:
            self.on_limit()
            return
        else:
            self.selected.append(photo_id)
        tile = self.tiles[photo_id]
        self._style(tile, photo_id in self.selected)
        safe_update(tile)
        if self.insert_button is not None:
            self.insert_button.content = self._insert_label()
            safe_update(self.insert_button)

    def confirm(self) -> None:
        """The chosen photos in the order of this screen (by event date)."""
        shown = [item["id"] for group in self.groups for item in group["photos"]]
        self.on_confirm([pid for pid in shown if pid in self.selected])
