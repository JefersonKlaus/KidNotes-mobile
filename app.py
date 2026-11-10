"""App controllers.

- `AppRoot`: the sign-in gate. Shows the sign-in / registration screen; once
  the teacher is signed in, opens their own encrypted data in `KidNotesApp`.
  Signing out closes that data and goes back to the sign-in screen.
- `KidNotesApp`: session state and navigation between screens. Routes:
  "class" (HOME: the principal class; children + "Add event") → "child"
  (learning story) → "extra_info" (notes about the child). "event_form" and
  "camera" create or edit an event. "reports" → "report_review" (edit a
  report) → "report_photos" (choose the images of the report).
  Side menu (☰ on home, or a swipe from the left edge): Home, "classes" (all
  classes: ★ sets the principal one) → "manage_class" (add/edit/remove
  students), "settings" (account, Groq API key), Sign out.
"""

import logging
import os
from datetime import date
from typing import Any

import flet as ft

from components import TopNotice
from database import AccountStore, Repositories, Session
from database.reports import MAX_REPORT_PHOTOS
from i18n import DEFAULT_LANGUAGE, FLUTTER_LOCALES, Translator, resolve_language
from media import GalleryPicker, camera_supported
from reports.ai import GroqClient, ReportAIError
from reports.document import build_report_pdf, report_filename
from reports.export import ReportExporter
from reports.generate import events_in_period, write_report
from reports.images import pdf_compatible
from screens.auth import LOGIN, AuthScreen
from screens.camera import CameraScreen, default_camera_factory
from screens.child import STORY_PAGE_SIZE, ChildScreen
from screens.class_form import NewClassForm
from screens.class_screen import MANAGE, ClassScreen, NoClassScreen, RemoveStudentDialog
from screens.classes import ClassesScreen
from screens.event_form import DiscardEventDialog, DraftPhoto, EventDraft, EventFormScreen
from screens.extra_info import ExtraInfoScreen
from screens.menu import build_menu
from screens.report_photos import ReportPhotosScreen
from screens.reports import DeleteReportDialog, ReportRequest, ReportReviewScreen, ReportScreen
from screens.settings import SettingsScreen
from screens.student_form import StudentForm
from theme import COLORS

logger = logging.getLogger(__name__)


def setup_page(page: ft.Page, tr: Translator) -> None:
    page.title = "RelatórioFácil Infantil"
    page.bgcolor = COLORS["background"]
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=COLORS["primary"], font_family="Nunito")
    # Keeps Flutter's built-in texts (tooltips, date picker...) in the same
    # language as the app. English first = fallback locale.
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=list(FLUTTER_LOCALES.values()),
        current_locale=tr.flutter_locale,
    )


SCREEN_ROOT = "screen-root"  # `data` of the layout that show_screen puts on the page


def show_screen(page: ft.Page, screen: Any, keep_scroll: bool = False) -> None:
    """Put a screen on the page: scrollable body + optional fixed bottom bar.

    `keep_scroll`: the same screen is shown again (after deleting, saving...).
    Its scrollable body is reused and only its content is replaced, so the
    page stays where the teacher was. A new body (a new screen) starts at the top.
    """
    content = screen.build()
    bottom_bar = screen.bottom_bar() if hasattr(screen, "bottom_bar") else None
    scrollable = getattr(screen, "scrollable", True)
    root = page.controls[-1] if page.controls else None
    if keep_scroll and scrollable and getattr(root, "data", None) == SCREEN_ROOT:
        column = root.content
        body = column.controls[0]
        if isinstance(body, ft.Column) and body.scroll is not None:
            body.controls = [content]
            column.controls = [body, *([bottom_bar] if bottom_bar else [])]
            page.update()
            return
    body: ft.Control = (
        ft.Column(controls=[content], expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)
        if scrollable
        else ft.Container(content=content, expand=True)
    )
    page.controls.clear()
    page.add(
        ft.SafeArea(
            content=ft.Column(
                controls=[body, *([bottom_bar] if bottom_bar else [])],
                expand=True,
                spacing=0,
            ),
            expand=True,
            data=SCREEN_ROOT,
        )
    )
    page.update()


class AppRoot:
    """Sign-in gate: the teacher's data is only opened after signing in."""

    def __init__(
        self,
        page: ft.Page,
        accounts: AccountStore,
        language: str = DEFAULT_LANGUAGE,
        gallery: Any = None,
        camera_factory: Any = default_camera_factory,
        exporter: Any = None,
        ai_client_factory: Any = GroqClient,
    ) -> None:
        self.page = page
        self.accounts = accounts
        self.language = language
        # Created once, inside the Flet session, so the services register with the page.
        self.gallery = gallery or GalleryPicker()
        self.exporter = exporter or ReportExporter()
        self.camera_factory = camera_factory
        self.ai_client_factory = ai_client_factory
        self.session: Session | None = None
        self.app: KidNotesApp | None = None
        self.auth_mode: str | None = None
        self.show_auth()

    def show_auth(self, mode: str | None = None) -> None:
        self.auth_mode = mode
        tr = Translator(self.language)
        setup_page(self.page, tr)
        self.page.drawer = None  # the side menu is only for the signed-in app
        self.page.on_locale_change = self._on_locale_change
        screen = AuthScreen(
            self.accounts,
            tr,
            on_authenticated=self._on_authenticated,
            on_switch_mode=self.show_auth,
            mode=mode,
        )
        show_screen(self.page, screen)

    def _on_authenticated(self, session: Session) -> None:
        self.session = session
        self.app = KidNotesApp(
            self.page,
            Repositories.from_database(session.database),
            self.language,
            gallery=self.gallery,
            camera_factory=self.camera_factory,
            account_email=session.email,
            on_sign_out=self.sign_out,
            exporter=self.exporter,
            ai_client_factory=self.ai_client_factory,
        )

    def sign_out(self) -> None:
        if self.app is not None:
            self.language = self.app.tr.language
        if self.session is not None:
            self.session.close()  # the teacher's data is closed (key dropped)
        self.session = None
        self.app = None
        self.show_auth(LOGIN)

    def _on_locale_change(self, event: ft.LocaleChangeEvent) -> None:
        """Device language changed while the sign-in screen was open."""
        language = resolve_language(event.locales)
        if language != self.language:
            self.language = language
            self.show_auth(self.auth_mode)


class KidNotesApp:
    def __init__(
        self,
        page: ft.Page,
        repositories: Repositories,
        language: str = DEFAULT_LANGUAGE,
        gallery: Any = None,
        camera_factory: Any = default_camera_factory,
        account_email: str = "",
        on_sign_out: Any = None,
        exporter: Any = None,
        ai_client_factory: Any = GroqClient,
    ) -> None:
        self.page = page
        self.repos = repositories
        self.tr = Translator(language)
        self.gallery = gallery or GalleryPicker()
        self.exporter = exporter or ReportExporter()
        self.ai_client_factory = ai_client_factory
        self.report_request: ReportRequest | None = None
        self.review_report_id: str | None = None
        self.review_draft: str | None = None
        self.photo_selection: list[str] = []  # on the "choose images" screen
        self.camera_factory = camera_factory
        self.account_email = account_email
        self.on_sign_out = on_sign_out
        self.route = "class"  # home: the principal class
        self.selected_class: dict[str, Any] | None = None  # the principal class (home)
        self.managed_class: dict[str, Any] | None = None  # opened on the Classes page
        self.selected_student: dict[str, Any] | None = None
        self.story_limit = STORY_PAGE_SIZE
        self.draft: EventDraft | None = None
        self.notes_draft: str | None = None  # text on the extra information screen
        self.notice = TopNotice(page)  # messages at the top ("Report deleted.")
        self.editing_groq_key = False  # Settings: the key field is open
        self.settings_back_route = "class"  # where Settings' ← goes
        self._rendered_route: str | None = None

        setup_page(page, self.tr)
        page.on_route_change = self._on_route_change
        page.on_locale_change = self._on_locale_change
        self._install_menu()
        self._load_principal_class()
        self.render()

    # --- language ----------------------------------------------------------------

    def _apply_locale(self) -> None:
        setup_page(self.page, self.tr)
        self._install_menu()  # its texts change language too

    def _on_locale_change(self, event: ft.LocaleChangeEvent) -> None:
        """Device language changed while the app was open."""
        language = resolve_language(event.locales)
        if language == self.tr.language:
            return
        self.tr = Translator(language)
        self._apply_locale()
        self.render()

    # --- rendering ---------------------------------------------------------------

    def render(self) -> None:
        screen = self._current_screen()
        # Same screen again (after deleting, saving...): keep the scroll position.
        same_screen = self.route == self._rendered_route
        self._rendered_route = self.route
        show_screen(self.page, screen, keep_scroll=same_screen)
        if isinstance(screen, CameraScreen):
            self.page.run_task(screen.start)  # the camera must be on the page first

    def notify(self, text: str, error: bool = False) -> None:
        """Information message at the top of the screen."""
        self.notice.show(text, error=error)

    def _current_screen(self) -> Any:
        if self.route == "settings":
            return self._settings_screen()
        if self.route == "report_photos" and self.review_report_id:
            screen = self._report_photos_screen()
            if screen is not None:
                return screen
        if self.route == "report_review" and self.review_report_id:
            screen = self._report_review_screen()
            if screen is not None:
                return screen
        if self.route == "reports" and self.report_request and self.selected_class:
            return self._report_screen()
        if self.route == "camera" and self.draft:
            return CameraScreen(
                self.tr,
                on_photo=self._on_photo_taken,
                on_close=lambda: self.navigate("event_form"),
                camera_factory=self.camera_factory,
            )
        if self.route == "event_form" and self.draft:
            return EventFormScreen(
                self.draft,
                self._event_form_students(),
                self.repos.events,
                self.tr,
                self.page,
                camera_available=camera_supported(self.page),
                on_take_photo=self.open_camera,
                on_pick_from_gallery=self.pick_photos_from_gallery,
                on_remove_photo=self.remove_draft_photo,
                on_saved=self._on_event_saved,
                on_cancel=self.cancel_event,
            )
        if self.route == "extra_info" and self.selected_student and self.notes_draft is not None:
            return ExtraInfoScreen(
                self.selected_student,
                self.notes_draft,
                self.repos.students,
                self.tr,
                on_change=self._on_notes_change,
                on_saved=self._on_extra_info_saved,
                on_back=self.close_extra_info,
            )
        if self.route == "child" and self.selected_student and self.selected_class:
            return self._child_screen()
        if self.route == "classes":
            return self._classes_screen()
        if self.route == "manage_class" and self.managed_class:
            return self._manage_class_screen()
        if self.selected_class is None:
            return NoClassScreen(self.tr, on_open_menu=self.open_menu,
                                 on_open_classes=self.open_classes)
        return ClassScreen(  # home: the principal class
            self.selected_class,
            self.repos.students.list_active(self.selected_class["id"]),
            [],
            self.repos.events.count_by_student(),
            self.tr,
            on_open_menu=self.open_menu,
            on_open_child=self.open_child,
            on_add_event=lambda: self.start_event(),
            on_open_reports=self.open_reports,
        )

    def _classes_screen(self) -> ClassesScreen:
        counts = self.repos.students.count_active_by_class()
        classes = [
            {**class_data, "student_count": counts.get(class_data["id"], 0)}
            for class_data in self.repos.classes.list_all()
        ]
        return ClassesScreen(
            classes,
            self.selected_class["id"] if self.selected_class else None,
            self.tr,
            on_open_menu=self.open_menu,
            on_manage_class=self.manage_class,
            on_set_default=self.set_default_class,
            on_add_class=self.show_add_class_dialog,
        )

    def _manage_class_screen(self) -> ClassScreen:
        assert self.managed_class is not None
        class_id = self.managed_class["id"]
        return ClassScreen(
            self.managed_class,
            self.repos.students.list_active(class_id),
            self.repos.students.list_inactive(class_id),
            self.repos.events.count_by_student(),
            self.tr,
            mode=MANAGE,
            on_back=lambda: self.navigate("classes"),
            on_add_student=self.show_add_student_dialog,
            on_edit_student=self.show_edit_student_dialog,
            on_remove_student=self.show_remove_student_dialog,
            on_reactivate_student=self.reactivate_student,
            is_default=bool(self.selected_class and self.selected_class["id"] == class_id),
            on_set_default=lambda: self.set_default_class(self.managed_class),
        )

    def _child_screen(self) -> ChildScreen:
        assert self.selected_student and self.selected_class
        student_id = self.selected_student["id"]
        events = self.repos.events.story(student_id, limit=self.story_limit + 1)
        names = {
            s["id"]: s["name"]
            for s in (self.repos.students.get(sid) for e in events for sid in e["student_ids"])
            if s
        }
        return ChildScreen(
            self.selected_student,
            self.selected_class,
            events[: self.story_limit],
            has_more=len(events) > self.story_limit,
            student_names=names,
            load_photo=self.repos.events.load_photo,
            on_back=lambda: self.navigate("class"),
            on_add_event=lambda: self.start_event(preselected=student_id),
            on_show_more=self.show_more_story,
            tr=self.tr,
            on_edit_event=self.edit_event,
            on_edit_notes=self.open_extra_info,
        )

    # --- navigation -------------------------------------------------------------

    def _load_principal_class(self) -> None:
        """Home shows the principal class; without one, the first class becomes it."""
        class_id = self.repos.settings.get_default_class_id()
        principal = self.repos.classes.get(class_id) if class_id else None
        if principal is None:
            classes = self.repos.classes.list_all()
            principal = classes[0] if classes else None
            if principal is not None:
                self._save_principal(principal)
        self.selected_class = principal

    def navigate(self, route: str) -> None:
        self.route = route
        self.render()

    def _on_route_change(self, _: ft.RouteChangeEvent) -> None:
        self.render()

    def go_home(self) -> None:
        self.navigate("class")

    def open_classes(self) -> None:
        self.navigate("classes")

    def manage_class(self, class_data: dict[str, Any]) -> None:
        """Classes page → a class: add, edit and remove its students."""
        self.managed_class = class_data
        self.navigate("manage_class")

    def set_default_class(self, class_data: dict[str, Any]) -> None:
        """★: the app opens on this class from now on (home)."""
        self._save_principal(class_data)
        self.selected_class = class_data
        self.render()
        self.notify(self.tr.t("classes.default_set", name=class_data["name"]))

    def _save_principal(self, class_data: dict[str, Any]) -> None:
        try:
            self.repos.settings.set_default_class_id(class_data["id"])
        except Exception:  # never block the app because of it
            logger.exception("Could not save the principal class.")

    def open_child(self, student: dict[str, Any]) -> None:
        self.selected_student = student
        self.story_limit = STORY_PAGE_SIZE
        self.navigate("child")

    # --- extra information (notes about the child) -------------------------------

    def open_extra_info(self) -> None:
        assert self.selected_student is not None
        self.notes_draft = self.selected_student.get("notes") or ""
        self.navigate("extra_info")

    def _on_notes_change(self, text: str) -> None:
        self.notes_draft = text  # kept if the screen is rebuilt (e.g. language change)

    def close_extra_info(self) -> None:
        """Back to the child: asks first if there is unsaved text."""
        saved = (self.selected_student or {}).get("notes") or ""
        if (self.notes_draft or "").strip() != saved.strip():
            dialog = DiscardEventDialog(
                self.tr,
                on_discard=self._discard_notes,
                on_keep=self.page.pop_dialog,
                prefix="discard_notes",
            )
            self.page.show_dialog(dialog.build())
            return
        self._leave_extra_info()

    def _discard_notes(self) -> None:
        self.page.pop_dialog()
        self._leave_extra_info()

    def _leave_extra_info(self) -> None:
        self.notes_draft = None
        self.navigate("child")

    def _on_extra_info_saved(self, student: dict[str, Any]) -> None:
        self.selected_student = student  # the child screen shows the new text
        self._leave_extra_info()
        self.notify(self.tr.t("child.extra_info_saved"))

    def show_more_story(self) -> None:
        self.story_limit += STORY_PAGE_SIZE
        self.render()

    # --- classes ---------------------------------------------------------------

    def show_add_class_dialog(self, _: ft.ControlEvent) -> None:
        form = NewClassForm(
            self.repos.classes,
            self.tr,
            on_saved=self._on_class_saved,
            on_cancel=self.page.pop_dialog,
        )
        self.page.show_dialog(form.build())

    def _on_class_saved(self, class_data: dict[str, Any]) -> None:
        self.page.pop_dialog()
        if self.selected_class is None:  # the first class becomes the principal one
            self._save_principal(class_data)
            self.selected_class = class_data
        self.render()  # the class list is read again from the database

    # --- students of the selected class ----------------------------------------

    def show_add_student_dialog(self) -> None:
        self._show_student_form(None)

    def show_edit_student_dialog(self, student: dict[str, Any]) -> None:
        self._show_student_form(student)

    def _show_student_form(self, student: dict[str, Any] | None) -> None:
        assert self.managed_class is not None
        form = StudentForm(
            self.repos.students,
            self.tr,
            self.page,
            class_id=self.managed_class["id"],
            student=student,
            on_saved=self._on_students_changed,
            on_cancel=self.page.pop_dialog,
        )
        self.page.show_dialog(form.build())

    def show_remove_student_dialog(self, student: dict[str, Any]) -> None:
        dialog = RemoveStudentDialog(
            self.repos.students,
            self.tr,
            student,
            on_removed=self._on_students_changed,
            on_cancel=self.page.pop_dialog,
        )
        self.page.show_dialog(dialog.build())

    def reactivate_student(self, student: dict[str, Any]) -> None:
        """Bring a transferred student back to the class."""
        try:
            self.repos.students.reactivate(student["id"])
        except Exception:
            logger.exception("Could not reactivate the student.")
            self.notify(self.tr.t("students.reactivate_error"), error=True)
            return
        self.render()
        self.notify(self.tr.t("students.reactivated", name=student["name"]))

    def _on_students_changed(self, _: dict[str, Any]) -> None:
        self.page.pop_dialog()
        self.render()  # the student list is read again from the database

    # --- events ------------------------------------------------------------------

    def start_event(self, preselected: str | None = None) -> None:
        """Open the event form (from the class screen, or from a child's story).

        From a child's story, that child comes already selected.
        """
        assert self.selected_class is not None
        child = self.repos.students.get(preselected) if preselected else None
        self.draft = EventDraft(
            class_id=self.selected_class["id"],
            return_route="child" if preselected else "class",
            context_label=child["name"] if child else self.selected_class["name"],
            student_ids={preselected} if preselected else set(),
            preselected_ids=frozenset({preselected} if preselected else ()),
        )
        self.navigate("event_form")

    def open_camera(self) -> None:
        """Open the camera screen, only where the camera can work."""
        if self.draft is None:
            return
        if not camera_supported(self.page):
            self._back_to_form_with(self.tr.t("event_form.camera_unsupported"))
            return
        try:
            self.navigate("camera")
        except ft.FletUnsupportedPlatformException:
            # Safety net in case flet-camera's platform rule changes.
            logger.exception("The camera is not supported here.")
            self._back_to_form_with(self.tr.t("event_form.camera_unsupported"))

    def _back_to_form_with(self, message: str) -> None:
        if self.draft is not None:
            self.draft.error = message
        self.navigate("event_form")

    def edit_event(self, event: dict[str, Any]) -> None:
        """Open an event of the child's story in the event form."""
        assert self.selected_class is not None and self.selected_student is not None
        self.draft = EventDraft(
            class_id=event["class_id"],
            return_route="child",
            context_label=self.selected_student["name"],
            student_ids=set(event["student_ids"]),
            preselected_ids=frozenset(event["student_ids"]),
            description=event["description"],
            occurred_on=event["occurred_on"],
            photos=[
                DraftPhoto(self.repos.events.load_photo(photo_id), photo_id)
                for photo_id in event["photo_ids"]
            ],
            event_id=event["id"],
        )
        self.navigate("event_form")

    def _event_form_students(self) -> list[dict[str, Any]]:
        """Children offered in the form: the active ones, plus (when editing) any
        transferred child already linked to the event, so they can be kept or removed."""
        assert self.draft is not None
        students = self.repos.students.list_active(self.draft.class_id)
        if self.draft.is_edit:
            students += [
                s for s in self.repos.students.list_inactive(self.draft.class_id)
                if s["id"] in self.draft.student_ids
            ]
        return students

    async def pick_photos_from_gallery(self, _: Any = None) -> None:
        if self.draft is None:
            return
        try:
            photos = await self.gallery.pick_photos()
        except Exception:
            logger.exception("Could not pick photos from the gallery.")
            self.draft.error = self.tr.t("event_form.error.gallery_failed")
            self.render()
            return
        if photos:
            self.draft.photos.extend(DraftPhoto(data) for data in photos)
            self.draft.changed = True
            self.draft.error = None
            self.render()

    def _on_photo_taken(self, data: bytes) -> None:
        if self.draft is not None:
            self.draft.photos.append(DraftPhoto(data))
            self.draft.changed = True
            self.draft.error = None
        self.navigate("event_form")

    def remove_draft_photo(self, index: int) -> None:
        if self.draft is not None and 0 <= index < len(self.draft.photos):
            del self.draft.photos[index]
            self.draft.changed = True
            self.render()

    def cancel_event(self) -> None:
        if self.draft is not None and self.draft.needs_discard_confirmation:
            dialog = DiscardEventDialog(
                self.tr,
                on_discard=self._discard_event,
                on_keep=self.page.pop_dialog,
                editing=self.draft.is_edit,
            )
            self.page.show_dialog(dialog.build())
            return
        self._close_event_form()

    def _discard_event(self) -> None:
        self.page.pop_dialog()
        self._close_event_form()

    def _on_event_saved(self, event: dict[str, Any]) -> None:
        edited = self.draft is not None and self.draft.is_edit
        self._close_event_form()
        message = self.tr.t("event_updated") if edited else self._saved_message(event)
        self.notify(message)

    def _saved_message(self, event: dict[str, Any]) -> str:
        """"Event saved to Clara's learning story." / "... of 3 students."."""
        student_ids = event["student_ids"]
        if len(student_ids) == 1:
            student = self.repos.students.get(student_ids[0])
            if student:
                return self.tr.t("event_saved.one", name=student["name"])
        return self.tr.t("event_saved.other", count=len(student_ids))

    def _close_event_form(self) -> None:
        return_route = self.draft.return_route if self.draft else "class"
        self.draft = None  # the photos in memory are released
        self.navigate(return_route)

    # --- reports -----------------------------------------------------------------------

    def _groq_key(self) -> str | None:
        """The teacher's key (saved encrypted); GROQ_API_KEY helps during development."""
        return self.repos.settings.get_groq_api_key() or os.environ.get("GROQ_API_KEY") or None

    def _groq_key_source(self) -> str:
        """Where the key comes from (for the log; never the key itself)."""
        if self.repos.settings.get_groq_api_key():
            return "the key saved in the app"
        return "GROQ_API_KEY (.env / terminal)" if os.environ.get("GROQ_API_KEY") else "nowhere"

    def _all_student_names(self, class_id: str) -> dict[str, str]:
        students = self.repos.students.list_active(class_id) + self.repos.students.list_inactive(
            class_id
        )
        return {s["id"]: s["name"] for s in students}

    def open_reports(self) -> None:
        assert self.selected_class is not None
        if self.report_request is None or self.report_request.class_id != self.selected_class["id"]:
            self.report_request = ReportRequest(
                class_id=self.selected_class["id"],
                instructions=self.repos.settings.get_report_instructions(),
            )
        self.navigate("reports")

    def _report_screen(self) -> ReportScreen:
        assert self.report_request is not None and self.selected_class is not None
        request = self.report_request
        students = self.repos.students.list_active(request.class_id)
        counts = {
            s["id"]: len(events_in_period(self.repos.events.story(s["id"]), request.start,
                                          request.end))
            for s in students
        }
        return ReportScreen(
            request,
            self.selected_class,
            students,
            counts,
            self.repos.reports.list_for_class(request.class_id),
            self._all_student_names(request.class_id),
            has_api_key=bool(self._groq_key()),
            tr=self.tr,
            page=self.page,
            on_back=lambda: self.navigate("class"),
            on_period_change=self.set_report_period,
            on_generate=self.generate_reports,
            on_open_settings=self.open_settings,
            on_open_report=self.open_report,
            on_save_instructions=self.save_report_instructions,
            on_delete_report=self.show_delete_report_dialog,
        )

    def show_delete_report_dialog(self, report: dict[str, Any]) -> None:
        student = self.repos.students.get(report["student_id"])
        dialog = DeleteReportDialog(
            self.repos.reports,
            self.tr,
            report,
            student["name"] if student else "?",
            on_deleted=self._on_report_deleted,
            on_cancel=self.page.pop_dialog,
        )
        self.page.show_dialog(dialog.build())

    def _on_report_deleted(self, report: dict[str, Any]) -> None:
        self.page.pop_dialog()
        logger.info("Report %s deleted.", report["id"])
        request = self.report_request
        if request is not None:
            # A "Report ready → Open" line pointing to it would open nothing.
            request.statuses = {
                sid: status for sid, status in request.statuses.items()
                if status != ("done", report["id"])
            }
        if self.review_report_id == report["id"]:
            self.review_report_id = None
            self.review_draft = None
        self.render()
        self.notify(self.tr.t("delete_report.done"))

    def save_report_instructions(self, text: str) -> None:
        """Kept (encrypted) for the next reports, in every class of this account."""
        if text.strip() == self.repos.settings.get_report_instructions():
            return
        try:
            self.repos.settings.set_report_instructions(text)
        except Exception:  # never block the report screen because of it
            logger.exception("Could not save the report instructions.")

    def set_report_period(self, start: date, end: date) -> None:
        assert self.report_request is not None
        self.report_request.start, self.report_request.end = start, end
        self.report_request.error = None
        self.render()

    # --- side menu and settings --------------------------------------------------------

    def _install_menu(self) -> None:
        """The side menu belongs to the page: ☰ on home, or a swipe from the left edge."""
        self.page.drawer = build_menu(
            self.tr, self.account_email, on_home=self._menu_home,
            on_classes=self._menu_classes, on_settings=self._menu_settings,
            on_sign_out=self._menu_sign_out,
        )

    async def open_menu(self, _: Any = None) -> None:
        await self.page.show_drawer()

    async def _menu_home(self, _: Any = None) -> None:
        await self.page.close_drawer()
        self.go_home()

    async def _menu_classes(self, _: Any = None) -> None:
        await self.page.close_drawer()
        self.open_classes()

    async def _menu_settings(self, _: Any = None) -> None:
        await self.page.close_drawer()
        self.open_settings()

    async def _menu_sign_out(self, _: Any = None) -> None:
        await self.page.close_drawer()
        if self.on_sign_out is not None:
            self.on_sign_out()

    def open_settings(self) -> None:
        if self.route != "settings":
            self.settings_back_route = self.route
        self.editing_groq_key = False
        self.navigate("settings")

    def _settings_screen(self) -> SettingsScreen:
        saved = bool(self.repos.settings.get_groq_api_key())
        return SettingsScreen(
            self.account_email,
            has_saved_key=saved,
            env_key_in_use=not saved and bool(os.environ.get("GROQ_API_KEY")),
            editing_key=self.editing_groq_key,
            tr=self.tr,
            on_back=lambda: self.navigate(self.settings_back_route),
            on_save_key=self.save_groq_key,
            on_change_key=self.change_groq_key,
            on_remove_key=self.remove_groq_key,
        )

    def save_groq_key(self, key: str) -> None:
        self.repos.settings.set_groq_api_key(key)
        self.editing_groq_key = False
        if self.report_request is not None:
            self.report_request.error = None  # "Add your key..." no longer applies
        self.render()
        self.notify(self.tr.t("settings.api_key_saved"))

    def change_groq_key(self) -> None:
        self.editing_groq_key = True
        self.render()

    def remove_groq_key(self) -> None:
        self.repos.settings.clear_groq_api_key()
        self.editing_groq_key = False
        self.render()
        self.notify(self.tr.t("settings.api_key_removed"))

    async def generate_reports(self, _: Any = None) -> None:
        """One report per selected student, one after the other, updating the screen."""
        request = self.report_request
        if request is None or request.running:
            return
        students = [
            s for s in self.repos.students.list_active(request.class_id)
            if s["id"] in request.student_ids
        ]
        key = self._groq_key()
        error = (
            "reports.error.no_students" if not students
            else "reports.error.invalid_period" if request.start > request.end
            else "reports.error.missing_key" if not key
            else None
        )
        request.error = self.tr.t(error) if error else None
        if error:
            self.render()
            return

        self.save_report_instructions(request.instructions)
        request.running = True
        request.statuses = {s["id"]: ("waiting", None) for s in students}
        self.render()
        client = self.ai_client_factory(key)
        logger.info(
            "Generating reports: %d student(s), period %s to %s, key from %s, "
            "teacher's instructions: %s.",
            len(students), request.start, request.end, self._groq_key_source(),
            f"{len(request.instructions.strip())} chars" if request.instructions.strip()
            else "none",
        )
        names = self._all_student_names(request.class_id)
        try:
            for student in students:
                events = events_in_period(
                    self.repos.events.story(student["id"]), request.start, request.end
                )
                if not events:
                    request.statuses[student["id"]] = ("no_events", None)
                    self.render()
                    continue
                request.statuses[student["id"]] = ("generating", None)
                self.render()
                classmates = [n for sid, n in names.items() if sid != student["id"]]
                try:
                    text = await write_report(
                        client, self.tr, student, events, request.start, request.end,
                        classmates, request.instructions,
                    )
                except ReportAIError as failure:
                    # Student id only: the name is personal data.
                    logger.warning(
                        "Report for student %s failed: %s (%s)",
                        student["id"], failure.code, failure.detail or "no detail",
                    )
                    request.statuses[student["id"]] = ("error", failure.code)
                    if failure.code in ("invalid_key", "missing_key", "model"):
                        # The same problem would happen for every student: stop here.
                        for sid, (state, _) in request.statuses.items():
                            if state == "waiting":
                                request.statuses[sid] = ("error", failure.code)
                        break
                    continue
                except Exception:
                    logger.exception("Report generation failed.")
                    request.statuses[student["id"]] = ("error", "service")
                    continue
                finally:
                    self.render()
                report = self.repos.reports.add(
                    request.class_id, student["id"], request.start, request.end, text,
                    len(events), getattr(client, "model", ""),
                )
                request.statuses[student["id"]] = ("done", report["id"])
                logger.info("Report for student %s ready (%d events).", student["id"], len(events))
                self.render()
        finally:
            request.running = False
            self.render()

    def open_report(self, report_id: str) -> None:
        report = self.repos.reports.get(report_id)
        if report is None:
            return
        self.review_report_id = report_id
        self.review_draft = report["text"]
        self.navigate("report_review")

    def _report_review_screen(self) -> ReportReviewScreen | None:
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return None
        student = self.repos.students.get(report["student_id"])
        self._review_screen = ReportReviewScreen(
            report,
            student["name"] if student else "?",
            self.review_draft if self.review_draft is not None else report["text"],
            self.tr,
            can_share=self.page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS),
            on_change=self._on_review_change,
            on_save_pdf=self.save_report_pdf,
            on_share_pdf=self.share_report_pdf,
            on_back=self.close_report_review,
            on_save_text=self.save_report_text,
            photos=[(pid, self.repos.events.load_photo(pid)) for pid in report["photo_ids"]],
            on_add_photos=self.open_report_photos,
            on_remove_photo=self.remove_report_photo,
        )
        return self._review_screen

    # --- images of a report ----------------------------------------------------------

    def _events_with_photos(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        """The child's events of the report period that have photos, oldest first."""
        events = events_in_period(
            self.repos.events.story(report["student_id"]),
            report["period_start"],
            report["period_end"],
        )
        return [e for e in reversed(events) if e["photo_ids"]]

    def open_report_photos(self) -> None:
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return
        self.photo_selection = list(report["photo_ids"])
        self.navigate("report_photos")

    def _report_photos_screen(self) -> ReportPhotosScreen | None:
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return None
        student = self.repos.students.get(report["student_id"])
        groups = []
        for event in self._events_with_photos(report):
            items = []
            for photo_id in event["photo_ids"]:
                data = self.repos.events.load_photo(photo_id)
                items.append({"id": photo_id, "data": data,
                              "supported": data is not None and pdf_compatible(data)})
            groups.append({
                "date": self.tr.format_date(event["occurred_on"]),
                "description": event["description"],
                "photos": items,
            })
        return ReportPhotosScreen(
            student["name"] if student else "?",
            self.tr.format_date(report["period_start"]),
            self.tr.format_date(report["period_end"]),
            groups,
            self.photo_selection,
            MAX_REPORT_PHOTOS,
            self.tr,
            on_confirm=self.insert_report_photos,
            on_back=lambda: self.navigate("report_review"),  # nothing changes
            on_limit=lambda: self.notify(
                self.tr.t("report_photos.max", count=MAX_REPORT_PHOTOS), error=True
            ),
        )

    def insert_report_photos(self, photo_ids: list[str]) -> None:
        """Saves the chosen images in the report, back to the report."""
        try:
            self.repos.reports.set_photos(self.review_report_id or "", photo_ids)
        except Exception:
            logger.exception("Could not save the report images.")
            self.notify(self.tr.t("report_photos.save_failed"), error=True)
            return
        self.navigate("report_review")
        self.notify(
            self.tr.plural("report_photos.inserted", len(photo_ids)) if photo_ids
            else self.tr.t("report_photos.none")
        )

    def remove_report_photo(self, photo_id: str) -> None:
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return
        try:
            self.repos.reports.set_photos(
                report["id"], [pid for pid in report["photo_ids"] if pid != photo_id]
            )
        except Exception:
            logger.exception("Could not remove the report image.")
            self.notify(self.tr.t("report_photos.save_failed"), error=True)
            return
        self.render()  # same screen: keeps the scroll position
        self.notify(self.tr.t("report_review.photo_removed"))

    def _report_photos_for_pdf(self, report: dict[str, Any]) -> list[tuple[bytes, str]]:
        """(bytes, caption = the event's date) of the report's images that still exist."""
        dates = {
            pid: self.tr.format_date(event["occurred_on"])
            for event in self.repos.events.story(report["student_id"])
            for pid in event["photo_ids"]
        }
        photos = []
        for photo_id in report["photo_ids"]:
            data = self.repos.events.load_photo(photo_id)
            if data is None:
                logger.warning("Report image %s is no longer available.", photo_id)
                continue
            photos.append((data, dates.get(photo_id, "")))
        return photos

    def _on_review_change(self, text: str) -> None:
        self.review_draft = text

    def _review_changed(self) -> bool:
        report = self.repos.reports.get(self.review_report_id or "")
        return report is not None and (self.review_draft or "") != report["text"]

    def save_report_text(self) -> None:
        """"Save text": keeps the teacher's edits (no PDF)."""
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return
        if not (self.review_draft or "").strip():
            self._review_screen.show_error(self.tr.t("report_review.text_required"))
            return
        try:
            if self._review_changed():
                self.repos.reports.update_text(report["id"], self.review_draft or "")
        except Exception:
            logger.exception("Could not save the report text.")
            self.notify(self.tr.t("report_review.save_failed"), error=True)
            return
        self._review_screen.show_error(None)
        self.notify(self.tr.t("report_review.saved"))

    def _report_pdf(self) -> tuple[bytes, str] | None:
        """Saves the edited text, then builds the PDF (None: nothing to export)."""
        report = self.repos.reports.get(self.review_report_id or "")
        if report is None:
            return None
        if not (self.review_draft or "").strip():
            self._review_screen.show_error(self.tr.t("report_review.text_required"))
            return None
        if self._review_changed():
            report = self.repos.reports.update_text(report["id"], self.review_draft or "")
        student = self.repos.students.get(report["student_id"]) or {"name": "?"}
        class_data = self.repos.classes.get(report["class_id"]) or {"name": ""}
        pdf = build_report_pdf(self.tr, student, class_data["name"], report,
                               photos=self._report_photos_for_pdf(report))
        return pdf, report_filename(student, report)

    async def save_report_pdf(self, _: Any = None) -> None:
        try:
            result = self._report_pdf()
            if result is None:
                return
            if await self.exporter.save(*result):
                self.notify(self.tr.t("report_review.pdf_saved"))
        except Exception:
            logger.exception("Could not save the PDF.")
            self.notify(self.tr.t("report_review.export_failed"), error=True)

    async def share_report_pdf(self, _: Any = None) -> None:
        try:
            result = self._report_pdf()
            if result is None:
                return
            await self.exporter.share(*result)
        except Exception:
            logger.exception("Could not share the PDF.")
            self.notify(self.tr.t("report_review.export_failed"), error=True)

    def close_report_review(self) -> None:
        if self._review_changed():
            dialog = DiscardEventDialog(
                self.tr,
                on_discard=self._discard_review,
                on_keep=self.page.pop_dialog,
                prefix="discard_report",
            )
            self.page.show_dialog(dialog.build())
            return
        self._leave_review()

    def _discard_review(self) -> None:
        self.page.pop_dialog()
        self._leave_review()

    def _leave_review(self) -> None:
        self.review_report_id = None
        self.review_draft = None
        self.navigate("reports" if self.report_request else "class")
