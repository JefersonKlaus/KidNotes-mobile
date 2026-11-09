"""Child screen: extra information about the child and their learning story
(significant events, newest first)."""

from typing import Any

import flet as ft

from components import avatar, bottom_action_bar, empty_state, page_header, photo
from i18n import Translator
from theme import COLORS

STORY_PAGE_SIZE = 10  # events shown at a time (photos are decrypted when shown)

# Event layout (ResponsiveRow, 12 columns). Below the "sm" breakpoint (576 px
# of available width: phones) photos and text take the full width, one below
# the other. From "sm" on (tablets, computers, phones in landscape) they are
# side by side: photos on the left, text on the right.
SIDE_BY_SIDE_FROM = ft.ResponsiveRowBreakpoint.SM
PHOTO_COLUMNS = {ft.ResponsiveRowBreakpoint.XS: 12, SIDE_BY_SIDE_FROM: 5}
TEXT_COLUMNS = {ft.ResponsiveRowBreakpoint.XS: 12, SIDE_BY_SIDE_FROM: 7}


class ChildScreen:
    def __init__(
        self,
        student: dict[str, Any],
        class_data: dict[str, Any],
        events: list[dict[str, Any]],
        has_more: bool,
        student_names: dict[str, str],
        load_photo: Any,
        on_back: Any,
        on_add_event: Any,
        on_show_more: Any,
        tr: Translator,
        on_edit_event: Any = None,
        on_edit_notes: Any = None,
    ) -> None:
        self.student = student
        self.class_data = class_data
        self.events = events
        self.has_more = has_more
        self.student_names = student_names
        self.load_photo = load_photo
        self.on_back = on_back
        self.on_add_event = on_add_event
        self.on_show_more = on_show_more
        self.on_edit_event = on_edit_event
        self.on_edit_notes = on_edit_notes
        self.tr = tr

    def build(self) -> ft.Column:
        story: list[ft.Control] = [
            ft.Text(
                self.tr.t("child.story_title"),
                size=18,
                weight=ft.FontWeight.W_700,
                color=COLORS["ink"],
            )
        ]
        if self.events:
            story += [self._event_card(event) for event in self.events]
            if self.has_more:
                story.append(
                    ft.TextButton(
                        self.tr.t("child.show_more"),
                        icon=ft.Icons.EXPAND_MORE,
                        on_click=lambda _: self.on_show_more(),
                    )
                )
        else:
            story.append(
                empty_state(
                    ft.Icons.AUTO_STORIES,
                    self.tr.t("child.empty_title"),
                    self.tr.t("child.empty_message", name=self.student["name"]),
                )
            )
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.student["name"],
                        self.class_data["name"],
                        on_back=lambda _: self.on_back(),
                        back_tooltip=self.tr.t("common.back"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[self._profile(), self._extra_info(), *story],
                        spacing=14,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        # Extra information next to "Add event": both within easy reach.
        return bottom_action_bar(
            self.tr.t("students.add_event"),
            ft.Icons.ADD_A_PHOTO,
            lambda _: self.on_add_event(),
            secondary=(
                (self.tr.t("child.extra_info"), ft.Icons.NOTE_ALT_OUTLINED,
                 lambda _: self.on_edit_notes())
                if self.on_edit_notes is not None
                else None
            ),
        )

    def _profile(self) -> ft.Row:
        birth_date = self.student.get("birth_date")
        details = (
            self.tr.t(
                "students.birth_info",
                age=self.tr.format_age(birth_date),
                date=self.tr.format_date(birth_date),
            )
            if birth_date
            else self.tr.t("students.no_birth_date")
        )
        return ft.Row(
            controls=[
                avatar(self.student["initials"], self.student["color"], size=64),
                ft.Column(
                    controls=[
                        ft.Text(
                            self.student["name"],
                            size=18,
                            weight=ft.FontWeight.W_700,
                            color=COLORS["ink"],
                        ),
                        ft.Text(details, size=13, color=COLORS["muted"]),
                    ],
                    spacing=4,
                    expand=True,
                ),
            ],
            spacing=14,
        )

    def _extra_info(self) -> ft.Container:
        """The saved extra information (free text, no date), if any.

        It is edited from the "Extra information" button in the bottom bar.
        """
        notes = self.student.get("notes") or ""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.NOTE_ALT_OUTLINED, size=18, color=COLORS["primary"]),
                            ft.Text(
                                self.tr.t("child.extra_info"),
                                size=13,
                                weight=ft.FontWeight.W_700,
                                color=COLORS["primary"],
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Text(notes, size=14, color=COLORS["ink"], selectable=True),
                ],
                spacing=6,
            ),
            bgcolor=COLORS["lavender"],
            border_radius=14,
            padding=14,
            visible=bool(notes),
            data="extra-info",
        )

    def _event_card(self, event: dict[str, Any]) -> ft.Container:
        date_row = ft.Row(
            controls=[
                ft.Icon(ft.Icons.EVENT, size=16, color=COLORS["primary"]),
                ft.Text(
                    self.tr.format_date(event["occurred_on"]),
                    size=13,
                    weight=ft.FontWeight.W_700,
                    color=COLORS["primary"],
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    icon_size=20,
                    icon_color=COLORS["muted"],
                    tooltip=self.tr.t("child.edit_event"),
                    on_click=lambda _: self.on_edit_event(event),
                    visible=self.on_edit_event is not None,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        photos = self._event_photos(event)
        text = self._event_text(event)
        if photos and text:
            # Phone: the text goes below the photos. Tablet/computer (more than
            # SIDE_BY_SIDE_FROM wide): the text goes to the right of the photos.
            photos.col = PHOTO_COLUMNS
            text.col = TEXT_COLUMNS
            body: ft.Control = ft.ResponsiveRow(
                controls=[photos, text],
                spacing=16,
                run_spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        else:
            body = photos or text or ft.Container()
        return ft.Container(
            content=ft.Column(controls=[date_row, body], spacing=10),
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=18,
            padding=14,
        )

    def _event_photos(self, event: dict[str, Any]) -> ft.Column | None:
        photos = [self.load_photo(photo_id) for photo_id in event["photo_ids"]]
        if not photos:
            return None
        unavailable = self.tr.t("child.photo_unavailable")
        if len(photos) == 1:
            content: ft.Control = photo(photos[0], unavailable, height=220)
        else:
            content = ft.Row(
                controls=[photo(p, unavailable, width=160, height=160) for p in photos],
                scroll=ft.ScrollMode.AUTO,
                spacing=8,
            )
        # STRETCH: a single photo fills the width of its column.
        return ft.Column(
            controls=[content], horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

    def _event_text(self, event: dict[str, Any]) -> ft.Column | None:
        controls: list[ft.Control] = []
        if event["description"]:
            controls.append(ft.Text(event["description"], size=14, color=COLORS["ink"]))
        others = [
            self.student_names.get(student_id, "?")
            for student_id in event["student_ids"]
            if student_id != self.student["id"]
        ]
        if others:
            controls.append(
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.GROUP_OUTLINED, size=16, color=COLORS["muted"]),
                        ft.Text(
                            self.tr.t("child.with", names=", ".join(others)),
                            size=12,
                            color=COLORS["muted"],
                            expand=True,
                        ),
                    ],
                    spacing=6,
                )
            )
        return ft.Column(controls=controls, spacing=8) if controls else None
