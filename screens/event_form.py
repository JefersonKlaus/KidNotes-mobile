"""Event form: photos, what happened, date and the children involved.

The form edits an `EventDraft` kept by the app controller, so nothing is lost
when the teacher goes to the camera screen and comes back. Photos stay in
memory until the event is saved; they are only written to disk encrypted.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import flet as ft

from components import bottom_action_bar, page_header, photo, safe_update, section_title
from database import EventValidationError
from database.events import DESCRIPTION_MAX_LENGTH, MIN_EVENT_DATE
from dates import to_local_date
from i18n import Translator
from theme import COLORS

logger = logging.getLogger(__name__)


@dataclass
class DraftPhoto:
    """A photo in the form: decrypted bytes (memory) and, if already saved, its id."""

    data: bytes | None
    photo_id: str | None = None  # None: new photo (camera/gallery), not saved yet


@dataclass
class EventDraft:
    class_id: str
    return_route: str  # screen to go back to: "class" or "child"
    context_label: str = ""  # shown under the title: the child's or the class's name
    student_ids: set[str] = field(default_factory=set)
    # Children already selected when the form opened (shown first).
    preselected_ids: frozenset[str] = field(default_factory=frozenset)
    description: str = ""
    occurred_on: date = field(default_factory=date.today)
    photos: list[DraftPhoto] = field(default_factory=list)
    error: str | None = None  # message shown above the save button
    event_id: str | None = None  # set when editing an existing event
    changed: bool = False  # anything edited since the form opened

    @property
    def is_edit(self) -> bool:
        return self.event_id is not None

    @property
    def has_content(self) -> bool:
        return bool(self.photos or self.description.strip())

    @property
    def needs_discard_confirmation(self) -> bool:
        """New event with photos/text, or an edited event with unsaved changes."""
        return self.changed if self.is_edit else self.has_content


class EventFormScreen:
    def __init__(
        self,
        draft: EventDraft,
        students: list[dict[str, Any]],
        repository: Any,
        tr: Translator,
        page: ft.Page,
        camera_available: bool,
        on_take_photo: Any,
        on_pick_from_gallery: Any,
        on_remove_photo: Any,
        on_saved: Any,
        on_cancel: Any,
    ) -> None:
        self.draft = draft
        self.students = students
        self.repository = repository
        self.tr = tr
        self.page = page
        self.camera_available = camera_available
        self.on_take_photo = on_take_photo
        self.on_pick_from_gallery = on_pick_from_gallery
        self.on_remove_photo = on_remove_photo
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.chips: dict[str, ft.Chip] = {}
        self.class_chip: ft.Chip | None = None
        self.date_field: ft.TextField | None = None
        self.error_text: ft.Text | None = None
        self.date_picker: ft.DatePicker | None = None

    # --- layout ------------------------------------------------------------------

    def build(self) -> ft.Column:
        self.error_text = ft.Text(
            self.draft.error or "", color=ft.Colors.ERROR, size=13, visible=bool(self.draft.error)
        )
        return ft.Column(
            controls=[
                ft.Container(
                    content=page_header(
                        self.tr.t("event_form.edit_title" if self.draft.is_edit
                                  else "event_form.title"),
                        self.draft.context_label,
                        on_back=lambda _: self.on_cancel(),
                        back_tooltip=self.tr.t("common.cancel"),
                    ),
                    padding=ft.Padding(left=12, right=20, top=20, bottom=10),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            section_title(self.tr.t("event_form.photos"), ft.Icons.PHOTO),
                            self._photos_section(),
                            self._description_field(),
                            self._date_field(),
                            self._children_section(),
                            self.error_text,
                        ],
                        spacing=14,
                        # Fields use the full width of the screen.
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    padding=ft.Padding(left=20, right=20, top=8, bottom=24),
                ),
            ],
            spacing=0,
        )

    def bottom_bar(self) -> ft.Control:
        return bottom_action_bar(self.tr.t("event_form.save"), ft.Icons.CHECK, self.save)

    def _photos_section(self) -> ft.Column:
        thumbnails = [
            ft.Stack(
                controls=[
                    photo(data, "", width=96, height=96),
                    ft.Container(
                        content=ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=16,
                            icon_color=ft.Colors.WHITE,
                            tooltip=self.tr.t("event_form.remove_photo"),
                            on_click=lambda _, i=index: self.on_remove_photo(i),
                        ),
                        bgcolor="#99000000",
                        border_radius=18,
                        width=32,
                        height=32,
                        alignment=ft.Alignment.CENTER,
                        right=2,
                        top=2,
                    ),
                ],
                width=96,
                height=96,
            )
            for index, data in enumerate(p.data for p in self.draft.photos)
        ]
        # Two equal options: take a picture OR choose one from the gallery.
        # Colors per state: a fixed color would hide the disabled look, so a
        # disabled button turns grey.
        def state_colors(enabled: str, disabled: str) -> dict[ft.ControlState, str]:
            return {ft.ControlState.DISABLED: disabled, ft.ControlState.DEFAULT: enabled}

        button_style = ft.ButtonStyle(
            bgcolor=state_colors(COLORS["mint"], COLORS["disabled"]),
            color=state_colors(COLORS["ink"], COLORS["disabled_text"]),
            icon_color=state_colors(COLORS["ink"], COLORS["disabled_text"]),
            shape=ft.RoundedRectangleBorder(radius=14),
        )
        options = ft.Row(
            controls=[
                ft.FilledButton(
                    self.tr.t("event_form.take_photo"),
                    icon=ft.Icons.PHOTO_CAMERA,
                    on_click=lambda _: self.on_take_photo(),
                    # Blocked where the camera can't work (e.g. desktop): see the hint below.
                    disabled=not self.camera_available,
                    height=52,
                    expand=True,
                    style=button_style,
                ),
                ft.FilledButton(
                    self.tr.t("event_form.gallery"),
                    icon=ft.Icons.PHOTO_LIBRARY,
                    on_click=self.on_pick_from_gallery,
                    height=52,
                    expand=True,
                    style=button_style,
                ),
            ],
            spacing=10,
        )
        hint = ft.Row(
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=COLORS["muted"]),
                ft.Text(
                    self.tr.t("event_form.camera_unsupported"),
                    size=12,
                    color=COLORS["muted"],
                    expand=True,
                ),
            ],
            spacing=6,
            visible=not self.camera_available,
        )
        return ft.Column(
            controls=[
                *([ft.Row(controls=thumbnails, wrap=True, spacing=8, run_spacing=8)]
                  if thumbnails else []),
                options,
                hint,
            ],
            spacing=10,
        )

    def _description_field(self) -> ft.TextField:
        return ft.TextField(
            label=self.tr.t("event_form.description_label"),
            hint_text=self.tr.t("event_form.description_hint"),
            value=self.draft.description,
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=DESCRIPTION_MAX_LENGTH,
            capitalization=ft.TextCapitalization.SENTENCES,
            border_radius=14,
            border_color=COLORS["border"],
            focused_border_color=COLORS["primary"],
            bgcolor=COLORS["surface"],
            on_change=self._on_description_change,
        )

    def _date_field(self) -> ft.TextField:
        self.date_field = ft.TextField(
            label=self.tr.t("event_form.date_label"),
            value=self.tr.format_date(self.draft.occurred_on),
            read_only=True,
            prefix_icon=ft.Icons.EVENT,
            border_radius=14,
            border_color=COLORS["border"],
            bgcolor=COLORS["surface"],
            on_click=self.open_date_picker,
        )
        return self.date_field

    def _children_section(self) -> ft.Column:
        # Children already selected when the form opened come first, so the
        # child of the story the teacher came from is visible right away.
        ordered = sorted(self.students, key=lambda s: s["id"] not in self.draft.preselected_ids)
        self.chips = {
            student["id"]: ft.Chip(
                label=ft.Text(student["name"]),
                selected=student["id"] in self.draft.student_ids,
                show_checkmark=True,
                selected_color=COLORS["primary"],
                check_color=ft.Colors.WHITE,
                on_select=lambda _, sid=student["id"]: self.toggle_student(sid),
            )
            for student in ordered
        }
        # Last option, after all the children: the whole class.
        self.class_chip = ft.Chip(
            label=ft.Text(self.tr.t("event_form.whole_class")),
            leading=ft.Icon(ft.Icons.GROUPS, size=18),
            selected=self._all_selected(),
            show_checkmark=True,
            selected_color=COLORS["primary"],
            check_color=ft.Colors.WHITE,
            border_side=ft.BorderSide(1, COLORS["primary"]),
            on_select=lambda _: self.toggle_whole_class(),
        )
        for chip in [*self.chips.values(), self.class_chip]:
            self._style_chip(chip)
        return ft.Column(
            controls=[
                section_title(self.tr.t("event_form.children"), ft.Icons.CHILD_CARE),
                ft.Row(
                    controls=[*self.chips.values(), self.class_chip],
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                ),
            ],
            spacing=8,
        )

    # --- interactions (update in place: no full re-render, photos aren't resent) ------

    def _on_description_change(self, event: Any) -> None:
        self.draft.description = event.control.value or ""
        self.draft.changed = True

    def toggle_student(self, student_id: str) -> None:
        self.draft.changed = True
        if student_id in self.draft.student_ids:
            self.draft.student_ids.discard(student_id)
        else:
            self.draft.student_ids.add(student_id)
        chip = self.chips.get(student_id)
        if chip is not None:
            chip.selected = student_id in self.draft.student_ids
            self._style_chip(chip)
            safe_update(chip)
        self._refresh_class_chip()

    def toggle_whole_class(self) -> None:
        """"Whole class" selects every child (tapped again when all are selected: clears)."""
        self._select_all(not self._all_selected())

    def _all_selected(self) -> bool:
        ids = {s["id"] for s in self.students}
        return bool(ids) and ids <= self.draft.student_ids

    def _select_all(self, selected: bool) -> None:
        self.draft.changed = True
        self.draft.student_ids = {s["id"] for s in self.students} if selected else set()
        for student_id, chip in self.chips.items():
            chip.selected = student_id in self.draft.student_ids
            self._style_chip(chip)
            safe_update(chip)
        self._refresh_class_chip()

    def _refresh_class_chip(self) -> None:
        """The "Whole class" chip is highlighted when every child is selected."""
        if self.class_chip is not None:
            self.class_chip.selected = self._all_selected()
            self._style_chip(self.class_chip)
            safe_update(self.class_chip)

    @staticmethod
    def _style_chip(chip: ft.Chip) -> None:
        """Selected children stand out: primary color with white text."""
        chip.label.color = ft.Colors.WHITE if chip.selected else COLORS["ink"]
        chip.label.weight = ft.FontWeight.W_700 if chip.selected else ft.FontWeight.NORMAL
        if isinstance(chip.leading, ft.Icon):
            chip.leading.color = ft.Colors.WHITE if chip.selected else COLORS["primary"]

    def open_date_picker(self, _: Any = None) -> None:
        self.date_picker = ft.DatePicker(
            value=self.draft.occurred_on,
            first_date=MIN_EVENT_DATE,
            last_date=date.today(),
            help_text=self.tr.t("event_form.date_label"),
            on_change=self._on_date_picked,
        )
        self.page.show_dialog(self.date_picker)

    def _on_date_picked(self, event: Any) -> None:
        value = getattr(event, "data", None)
        if value is None and self.date_picker is not None:
            value = self.date_picker.value
        picked = to_local_date(value)
        if picked:
            self.draft.occurred_on = picked
            self.draft.changed = True
            if self.date_field is not None:
                self.date_field.value = self.tr.format_date(picked)
                safe_update(self.date_field)

    def show_error(self, message: str | None) -> None:
        self.draft.error = message
        if self.error_text is not None:
            self.error_text.value = message or ""
            self.error_text.visible = bool(message)
            safe_update(self.error_text)

    def save(self, _: Any = None) -> None:
        try:
            if self.draft.event_id:
                event = self.repository.update(
                    self.draft.event_id,
                    self.draft.student_ids,
                    self.draft.description,
                    self.draft.occurred_on,
                    # Saved photos are kept by id; new ones are sent as bytes.
                    [p.photo_id or p.data for p in self.draft.photos],
                )
            else:
                event = self.repository.add(
                    self.draft.class_id,
                    self.draft.student_ids,
                    self.draft.description,
                    self.draft.occurred_on,
                    [p.data for p in self.draft.photos],
                )
        except EventValidationError as error:
            self.show_error(self.tr.t(f"event_form.error.{error.code}"))
            return
        except Exception:
            logger.exception("Could not save the event.")
            self.show_error(self.tr.t("event_form.error.save_failed"))
            return
        self.on_saved(event)


class DiscardEventDialog:
    """Asks before throwing away a new event with photos/text, or unsaved edits."""

    def __init__(
        self,
        tr: Translator,
        on_discard: Any,
        on_keep: Any,
        editing: bool = False,
        prefix: str | None = None,  # texts "<prefix>.title" / "<prefix>.message"
    ) -> None:
        self.tr = tr
        self.on_discard = on_discard
        self.on_keep = on_keep
        self.prefix = prefix or ("discard_changes" if editing else "discard_event")

    def build(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.t(f"{self.prefix}.title")),
            content=ft.Text(self.tr.t(f"{self.prefix}.message")),
            actions=[
                ft.TextButton(self.tr.t("discard_event.keep"), on_click=lambda _: self.on_keep()),
                ft.FilledButton(
                    self.tr.t("discard_event.confirm"),
                    on_click=lambda _: self.on_discard(),
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
