"""App controllers.

- `AppRoot`: the sign-in gate. Shows the sign-in / registration screen; once
  the teacher is signed in, opens their own encrypted data in `KidNotesApp`.
  Signing out closes that data and goes back to the sign-in screen.
- `KidNotesApp`: session state and navigation between screens. Routes:
  "classes" (home) → "class" (children + "Add event") → "child" (learning
  story) → "extra_info" (notes about the child). "event_form" and "camera"
  create or edit an event.
"""

import logging
import os
from datetime import date
from typing import Any

import flet as ft

from components import info_message
from database import AccountStore, Repositories, Session
from i18n import DEFAULT_LANGUAGE, FLUTTER_LOCALES, Translator, resolve_language
from media import GalleryPicker, camera_supported
from reports.ai import GroqClient, ReportAIError
from reports.document import build_report_pdf, report_filename
from reports.export import ReportExporter
from reports.generate import events_in_period, write_report
from screens.auth import LOGIN, AuthScreen
from screens.camera import CameraScreen, default_camera_factory
from screens.child import STORY_PAGE_SIZE, ChildScreen
from screens.class_form import NewClassForm
from screens.class_screen import ClassScreen, RemoveStudentDialog
from screens.dashboard import DashboardScreen
from screens.event_form import DiscardEventDialog, DraftPhoto, EventDraft, EventFormScreen
from screens.extra_info import ExtraInfoScreen
from screens.reports import ReportRequest, ReportReviewScreen, ReportScreen
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


def show_screen(page: ft.Page, screen: Any) -> None:
    """Put a screen on the page: scrollable body + optional fixed bottom bar."""
    content = screen.build()
    bottom_bar = screen.bottom_bar() if hasattr(screen, "bottom_bar") else None
    body: ft.Control = (
        ft.Column(controls=[content], expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)
        if getattr(screen, "scrollable", True)
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
        self.camera_factory = camera_factory
        self.account_email = account_email
        self.on_sign_out = on_sign_out
        self.route = "classes"
        self.selected_class: dict[str, Any] | None = None
        self.selected_student: dict[str, Any] | None = None
        self.story_limit = STORY_PAGE_SIZE
        self.draft: EventDraft | None = None
        self.notes_draft: str | None = None  # text on the extra information screen

        setup_page(page, self.tr)
        page.on_route_change = self._on_route_change
        page.on_locale_change = self._on_locale_change
        self._restore_last_class()
        self.render()

    # --- language ----------------------------------------------------------------

    def _apply_locale(self) -> None:
        setup_page(self.page, self.tr)

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
        show_screen(self.page, screen)
        if isinstance(screen, CameraScreen):
            self.page.run_task(screen.start)  # the camera must be on the page first

    def _current_screen(self) -> Any:
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
        if self.route == "class" and self.selected_class:
            return ClassScreen(
                self.selected_class,
                self.repos.students.list_active(self.selected_class["id"]),
                self.repos.students.list_inactive(self.selected_class["id"]),
                self.repos.events.count_by_student(),
                on_back=lambda: self.navigate("classes"),
                on_open_child=self.open_child,
                on_add_student=self.show_add_student_dialog,
                on_edit_student=self.show_edit_student_dialog,
                on_remove_student=self.show_remove_student_dialog,
                on_reactivate_student=self.reactivate_student,
                on_add_event=lambda: self.start_event(),
                tr=self.tr,
                on_open_reports=self.open_reports,
            )
        counts = self.repos.students.count_active_by_class()
        classes = [
            {**class_data, "student_count": counts.get(class_data["id"], 0)}
            for class_data in self.repos.classes.list_all()
        ]
        return DashboardScreen(
            self.account_email,
            classes,
            on_class_selected=self.open_class,
            on_add_class=self.show_add_class_dialog,
            tr=self.tr,
            on_sign_out=self.on_sign_out,
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

    def _restore_last_class(self) -> None:
        """Start on the class the teacher chose last time (if it still exists)."""
        class_id = self.repos.settings.get_last_class_id()
        last_class = self.repos.classes.get(class_id) if class_id else None
        if last_class:
            self.selected_class = last_class
            self.route = "class"

    def navigate(self, route: str) -> None:
        self.route = route
        self.render()

    def _on_route_change(self, _: ft.RouteChangeEvent) -> None:
        self.render()

    def open_class(self, class_data: dict[str, Any]) -> None:
        self.selected_class = class_data
        try:
            self.repos.settings.set_last_class_id(class_data["id"])
        except Exception:  # remembering the class must never block navigation
            logger.exception("Could not save the last opened class.")
        self.navigate("class")

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
        self.page.show_dialog(info_message(self.tr.t("child.extra_info_saved")))

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

    def _on_class_saved(self, _: dict[str, Any]) -> None:
        self.page.pop_dialog()
        self.render()  # the home list is read again from the database

    # --- students of the selected class ----------------------------------------

    def show_add_student_dialog(self) -> None:
        self._show_student_form(None)

    def show_edit_student_dialog(self, student: dict[str, Any]) -> None:
        self._show_student_form(student)

    def _show_student_form(self, student: dict[str, Any] | None) -> None:
        assert self.selected_class is not None
        form = StudentForm(
            self.repos.students,
            self.tr,
            self.page,
            class_id=self.selected_class["id"],
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
            self.page.show_dialog(
                info_message(self.tr.t("students.reactivate_error"), error=True)
            )
            return
        self.render()
        self.page.show_dialog(
            info_message(self.tr.t("students.reactivated", name=student["name"]))
        )

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
        self.page.show_dialog(info_message(message))

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

    def _all_student_names(self, class_id: str) -> dict[str, str]:
        students = self.repos.students.list_active(class_id) + self.repos.students.list_inactive(
            class_id
        )
        return {s["id"]: s["name"] for s in students}

    def open_reports(self) -> None:
        assert self.selected_class is not None
        if self.report_request is None or self.report_request.class_id != self.selected_class["id"]:
            self.report_request = ReportRequest(class_id=self.selected_class["id"])
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
            on_save_key=self.save_groq_key,
            on_change_key=self.change_groq_key,
            on_open_report=self.open_report,
        )

    def set_report_period(self, start: date, end: date) -> None:
        assert self.report_request is not None
        self.report_request.start, self.report_request.end = start, end
        self.report_request.error = None
        self.render()

    def save_groq_key(self, key: str) -> None:
        assert self.report_request is not None
        self.repos.settings.set_groq_api_key(key)
        self.report_request.editing_key = False
        self.report_request.error = None
        self.render()
        self.page.show_dialog(info_message(self.tr.t("reports.api_key_saved")))

    def change_groq_key(self) -> None:
        assert self.report_request is not None
        self.report_request.editing_key = True
        self.render()

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

        request.running = True
        request.statuses = {s["id"]: ("waiting", None) for s in students}
        self.render()
        client = self.ai_client_factory(key)
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
                        client, self.tr, student, events, request.start, request.end, classmates
                    )
                except ReportAIError as failure:
                    request.statuses[student["id"]] = ("error", failure.code)
                    if failure.code in ("invalid_key", "missing_key"):
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
        )
        return self._review_screen

    def _on_review_change(self, text: str) -> None:
        self.review_draft = text

    def _review_changed(self) -> bool:
        report = self.repos.reports.get(self.review_report_id or "")
        return report is not None and (self.review_draft or "") != report["text"]

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
        pdf = build_report_pdf(self.tr, student, class_data["name"], report)
        return pdf, report_filename(student, report)

    async def save_report_pdf(self, _: Any = None) -> None:
        try:
            result = self._report_pdf()
            if result is None:
                return
            if await self.exporter.save(*result):
                self.page.show_dialog(info_message(self.tr.t("report_review.pdf_saved")))
        except Exception:
            logger.exception("Could not save the PDF.")
            self.page.show_dialog(
                info_message(self.tr.t("report_review.export_failed"), error=True)
            )

    async def share_report_pdf(self, _: Any = None) -> None:
        try:
            result = self._report_pdf()
            if result is None:
                return
            await self.exporter.share(*result)
        except Exception:
            logger.exception("Could not share the PDF.")
            self.page.show_dialog(
                info_message(self.tr.t("report_review.export_failed"), error=True)
            )

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
