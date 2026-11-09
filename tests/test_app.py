"""End-to-end tests of the app in both languages.

Everything runs against a real encrypted database in a temporary folder. The
phone's camera and photo picker are replaced by fakes (tests/conftest.py).
"""

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import flet as ft
import flet_camera as fc
import pytest

import main
from app import AppRoot, KidNotesApp
from theme import COLORS
from tests.conftest import (
    JPEG,
    PNG,
    FakeCamera,
    FakeGallery,
    auth_fields,
    collect_texts,
    fill,
    find_all,
    find_button,
    screen_text,
    sign_in,
    sign_up,
)


def start(page, repositories, language="en", gallery=None, camera=None):
    return KidNotesApp(
        page,
        repositories,
        language,
        gallery=gallery or FakeGallery(),
        camera_factory=lambda: camera or FakeCamera(),
    )


def by_name(repositories, class_id, name):
    return next(s for s in repositories.students.list_active(class_id) if s["name"] == name)


# --- language ---------------------------------------------------------------------------


PT_LABELS = {"email": "E-mail", "password": "Senha", "confirm": "Confirme a senha",
             "create": "Criar conta"}
EN_LABELS = {"email": "Email", "password": "Password", "confirm": "Confirm password",
             "create": "Create account"}


@pytest.mark.parametrize(
    ("device_locale", "labels", "subtitle", "title"),
    [
        (ft.Locale("en", "US"), EN_LABELS, "Create your account to start.", "Your classes"),
        (ft.Locale("pt", "BR"), PT_LABELS, "Crie sua conta para começar.", "Suas turmas"),
        (ft.Locale("de"), EN_LABELS, "Create your account to start.", "Your classes"),
    ],
)
def test_app_starts_in_the_device_language(make_page, device_locale, labels, subtitle, title):
    page = make_page([device_locale])
    asyncio.run(main.main(page))
    assert subtitle in screen_text(page)  # first use: create the account

    fields = auth_fields(page)
    fill(fields[labels["email"]], "ana@school.org")
    fill(fields[labels["password"]], "secret-pass")
    fill(fields[labels["confirm"]], "secret-pass")
    find_button(page.controls[-1], labels["create"]).on_click(None)

    assert title in screen_text(page)


@pytest.mark.parametrize(
    ("language", "expected", "unexpected"),
    [
        ("en", ["5 children", "Add event", "Add student", "Learning story"], ["crianças"]),
        ("pt", ["5 crianças", "Adicionar evento", "Adicionar aluno", "História de aprendizagem"],
         ["children"]),
    ],
)
def test_class_and_child_screens_are_translated(
    make_page, repositories, sample_class, language, expected, unexpected
):
    page = make_page()
    app = start(page, repositories, language)

    app.open_class(sample_class)
    texts = [screen_text(page)]
    app.open_child(repositories.students.list_active(sample_class["id"])[0])
    texts.append(screen_text(page))

    everything = " | ".join(texts)
    for text in expected:
        assert text in everything
    for text in unexpected:
        assert text not in everything


def test_device_language_change_while_running(make_page, repositories):
    page = make_page()
    app = start(page, repositories, "en")

    event = ft.LocaleChangeEvent(
        name="locale_change", control=page, locales=[ft.Locale("pt", "BR")]
    )
    app._on_locale_change(event)

    assert app.tr.language == "pt"
    assert page.locale_configuration.current_locale == ft.Locale("pt")
    assert "Suas turmas" in screen_text(page)


# --- home --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "empty_title"), [("en", "No classes yet"), ("pt", "Nenhuma turma ainda")]
)
def test_home_shows_empty_state_when_database_has_no_classes(
    make_page, repositories, language, empty_title
):
    page = make_page()
    start(page, repositories, language)

    assert empty_title in screen_text(page)


def test_home_lists_classes_with_their_active_student_count(make_page, repositories, sample_class):
    other = repositories.classes.add("Preschool II - Afternoon", "#B8DCEB")
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.students.deactivate(alice["id"])
    page = make_page()

    start(page, repositories, "en")

    text = screen_text(page)
    assert text.index(sample_class["name"]) < text.index(other["name"])
    assert "4 children" in text  # 5 students, 1 removed
    assert "0 children" in text


# --- new class form ----------------------------------------------------------------------


def class_form_parts(page):
    """(name field, save button, cancel button) of the open class form."""
    dialog = page.dialog
    cancel_button, save_button = dialog.actions
    return dialog.content.controls[0], save_button, cancel_button


@pytest.mark.parametrize(("language", "title"), [("en", "New class"), ("pt", "Nova turma")])
def test_new_class_form_is_translated(make_page, repositories, language, title):
    page = make_page()
    app = start(page, repositories, language)

    app.show_add_class_dialog(None)

    assert title in collect_texts(page.dialog)


def test_new_class_form_saves_to_the_database_and_updates_the_home(make_page, repositories):
    page = make_page()
    app = start(page, repositories, "en")
    app.show_add_class_dialog(None)
    name_field, save_button, _ = class_form_parts(page)

    name_field.value = "  Preschool   III - Morning "
    page.dialog.content.controls[2].controls[2].on_click(None)  # pick the third color
    save_button.on_click(None)

    saved = repositories.classes.list_all()
    assert [(c["name"], c["color"]) for c in saved] == [("Preschool III - Morning", "#B8E0C8")]
    assert page.dialog is None
    assert "Preschool III - Morning" in screen_text(page)


@pytest.mark.parametrize(
    ("language", "message"),
    [("en", "Enter the class name."), ("pt", "Informe o nome da turma.")],
)
def test_new_class_form_requires_a_name(make_page, repositories, language, message):
    page = make_page()
    app = start(page, repositories, language)
    app.show_add_class_dialog(None)
    name_field, save_button, _ = class_form_parts(page)

    name_field.value = "   "
    save_button.on_click(None)

    assert name_field.error == message
    assert repositories.classes.list_all() == []


def test_new_class_form_shows_an_error_when_saving_fails(make_page, repositories, database):
    page = make_page()
    app = start(page, repositories, "en")
    app.show_add_class_dialog(None)
    name_field, save_button, _ = class_form_parts(page)
    database.close()  # simulate a storage failure

    name_field.value = "Preschool I"
    save_button.on_click(None)

    assert name_field.error == "Couldn't save the class. Please try again."
    assert page.dialog is not None


def test_new_class_form_cancel_closes_without_saving(make_page, repositories):
    page = make_page()
    app = start(page, repositories, "en")
    app.show_add_class_dialog(None)
    name_field, _, cancel_button = class_form_parts(page)

    name_field.value = "Not saved"
    cancel_button.on_click(None)

    assert page.dialog is None
    assert repositories.classes.list_all() == []


# --- class screen ---------------------------------------------------------------------------


def open_class_screen(page, repositories, class_data, language="en", **kwargs):
    app = start(page, repositories, language, **kwargs)
    app.open_class(class_data)
    return app


def layout(page):
    """(scrollable body, fixed bottom bar or None) of the current screen."""
    column = page.controls[-1].content
    body = column.controls[0]
    return body, (column.controls[1] if len(column.controls) > 1 else None)


def student_form_parts(page):
    """(name field, birth field, save button, cancel button) of the open student form."""
    dialog = page.dialog
    name_field, birth_field = dialog.content.controls
    cancel_button, save_button = dialog.actions
    return name_field, birth_field, save_button, cancel_button


def pick_date(page, field, value):
    """Tap a date field, choose `value` in the date picker and confirm."""
    field.on_click(None)
    picker = page.dialog
    assert isinstance(picker, ft.DatePicker)
    page.pop_dialog()  # the picker closes itself after confirming
    picker.on_change(SimpleNamespace(data=value))
    return picker


def student_card(page, name):
    cards = find_all(
        page.controls[-1],
        lambda c: isinstance(c, ft.Container)
        and isinstance(c.content, ft.Row)
        and any(isinstance(x, ft.PopupMenuButton) for x in c.content.controls)
        and name in collect_texts(c),
    )
    assert len(cards) == 1, f"card of {name!r} not found"
    return cards[0]


def menu_item(page, student_name, label):
    """The item `label` of the "more options" menu on the card of `student_name`."""
    menu = next(
        c for c in student_card(page, student_name).content.controls
        if isinstance(c, ft.PopupMenuButton)
    )
    return next(item for item in menu.items if item.content == label)


def test_class_screen_layout(make_page, repositories, sample_class):
    """"Add student" is at the top; "Add event" is in the fixed bottom action bar."""
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    body, bottom_bar = layout(page)
    body_text = screen_text(page).split("|")
    assert bottom_bar is not None
    assert find_button(bottom_bar, "Add event") is not None
    assert find_button(body, "Add event") is None
    [add_student] = find_all(body, lambda c: isinstance(c, ft.IconButton)
                             and c.tooltip == "Add student")
    assert isinstance(add_student, ft.OutlinedIconButton)
    first_child = next(i for i, t in enumerate(body_text) if "Alice Martins" in t)
    assert next(i for i, t in enumerate(body_text) if "Add student" in t) < first_child


@pytest.mark.parametrize(
    ("language", "title"), [("en", "No students yet"), ("pt", "Nenhum aluno ainda")]
)
def test_class_screen_empty_state(make_page, repositories, language, title):
    empty_class = repositories.classes.add("Empty class")
    page = make_page()

    open_class_screen(page, repositories, empty_class, language)

    assert title in screen_text(page)
    assert layout(page)[1] is None  # no "Add event" without children


def test_class_screen_lists_active_students_alphabetically(make_page, repositories, sample_class):
    repositories.students.add(sample_class["id"], "Álvaro Lima", date(2021, 3, 14))
    page = make_page()

    open_class_screen(page, repositories, sample_class)

    text = screen_text(page)
    order = ["Alice Martins", "Álvaro Lima", "Bento Oliveira", "Luna Costa"]
    assert [text.index(n) for n in order] == sorted(text.index(n) for n in order)
    assert "Born 03/14/2021" in text
    assert "Birth date not set" in text
    assert "No events yet" in text


def test_class_screen_shows_each_childs_event_count(make_page, repositories, sample_class):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    bento = by_name(repositories, sample_class["id"], "Bento Oliveira")
    both = [alice["id"], bento["id"]]
    repositories.events.add(sample_class["id"], both, "Block tower", date.today())
    repositories.events.add(sample_class["id"], [alice["id"]], "First words", date.today())
    page = make_page()

    open_class_screen(page, repositories, sample_class)

    assert "2 events" in collect_texts(student_card(page, "Alice Martins"))
    assert "1 event" in collect_texts(student_card(page, "Bento Oliveira"))


def test_add_student_from_the_top_button(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    icon_button(page, "Add student").on_click(None)
    name_field, birth_field, save_button, _ = student_form_parts(page)
    assert page.dialog.title.value == "New student"
    name_field.value = "Maya  Rocha"
    picker = pick_date(page, birth_field, datetime(2021, 8, 5))
    assert picker.last_date == date.today()  # future dates can't be picked
    assert birth_field.value == "08/05/2021"
    save_button.on_click(None)

    maya = by_name(repositories, sample_class["id"], "Maya Rocha")
    assert maya["birth_date"] == date(2021, 8, 5)
    assert page.dialog is None
    assert "Maya Rocha" in screen_text(page)


@pytest.mark.parametrize(
    ("language", "message"),
    [("en", "Enter the student's name."), ("pt", "Informe o nome do aluno.")],
)
def test_add_student_requires_a_name(make_page, repositories, sample_class, language, message):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, language)

    app.show_add_student_dialog()
    name_field, _, save_button, _ = student_form_parts(page)
    save_button.on_click(None)

    assert name_field.error == message
    assert len(repositories.students.list_active(sample_class["id"])) == 5


def test_birth_date_in_the_future_is_rejected(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.show_add_student_dialog()
    name_field, birth_field, save_button, _ = student_form_parts(page)

    name_field.value = "Time Traveler"
    pick_date(page, birth_field, datetime.now() + timedelta(days=2))
    save_button.on_click(None)

    assert birth_field.error == "The birth date can't be in the future."
    names = [s["name"] for s in repositories.students.list_active(sample_class["id"])]
    assert "Time Traveler" not in names


def test_edit_student_updates_name_and_birth_date(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    menu_item(page, "Bento Oliveira", "Edit").on_click(None)
    name_field, birth_field, save_button, _ = student_form_parts(page)
    assert page.dialog.title.value == "Edit student"
    name_field.value = "Bento Oliveira Souza"
    pick_date(page, birth_field, date(2020, 1, 31))
    save_button.on_click(None)

    students = {s["name"]: s for s in repositories.students.list_active(sample_class["id"])}
    assert students["Bento Oliveira Souza"]["birth_date"] == date(2020, 1, 31)
    assert len(students) == 5  # edited, not duplicated


def test_edit_can_clear_the_birth_date(make_page, repositories, sample_class):
    zoe = repositories.students.add(sample_class["id"], "Zoe Prado", date(2021, 1, 1))
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    menu_item(page, "Zoe Prado", "Edit").on_click(None)
    _, birth_field, save_button, _ = student_form_parts(page)
    birth_field.suffix_icon.on_click(None)  # the "clear date" button
    save_button.on_click(None)

    assert repositories.students.get(zoe["id"])["birth_date"] is None


def transferred_card(page, name):
    cards = find_all(
        page.controls[-1],
        lambda c: isinstance(c, ft.Container)
        and c.bgcolor == COLORS["inactive_surface"]
        and name in collect_texts(c),
    )
    assert len(cards) == 1, f"transferred card of {name!r} not found"
    return cards[0]


@pytest.mark.parametrize(
    ("language", "remove", "group", "transferred_on", "reactivate"),
    [
        ("en", "Remove from class", "Transferred students (1)", "Transferred on", "Reactivate"),
        ("pt", "Remover da turma", "Alunos transferidos (1)", "Transferido(a) em", "Reativar"),
    ],
)
def test_removed_student_stays_on_the_class_screen_as_transferred(
    make_page, repositories, sample_class, language, remove, group, transferred_on, reactivate
):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, language)
    clara = by_name(repositories, sample_class["id"], "Clara Souza")

    menu_item(page, "Clara Souza", remove).on_click(None)
    page.dialog.actions[1].on_click(None)  # confirm

    assert page.dialog is None
    assert repositories.students.get(clara["id"])["active"] is False  # kept, not deleted
    text = screen_text(page)
    assert group in text
    card = transferred_card(page, "Clara Souza")
    today = app.tr.format_date(date.today())
    assert f"{transferred_on} {today}" in collect_texts(card)
    # Grey, no menu, not clickable; only "Reactivate".
    assert card.content.controls[0].bgcolor == COLORS["disabled"]  # grey avatar
    name = find_all(card, lambda c: isinstance(c, ft.Text) and c.value == "Clara Souza")[0]
    assert name.color == COLORS["disabled_text"]
    assert not find_all(card, lambda c: isinstance(c, ft.PopupMenuButton))
    assert card.on_click is None
    assert isinstance(find_button(card, reactivate), ft.OutlinedButton)
    # Listed after the active children, and not counted as active.
    assert text.index(group) > text.index("Luna Costa")
    assert ("4 children" if language == "en" else "4 crianças") in text


def test_transferred_students_cannot_be_linked_to_new_events(make_page, repositories, sample_class):
    repositories.students.deactivate(by_name(repositories, sample_class["id"], "Clara Souza")["id"])
    page = make_page()
    open_class_screen(page, repositories, sample_class).start_event()

    assert "Clara Souza" not in event_form(page).chips


@pytest.mark.parametrize(
    ("language", "message"),
    [("en", "Clara Souza is back in the class."), ("pt", "Clara Souza voltou para a turma.")],
)
def test_reactivate_a_transferred_student(make_page, repositories, sample_class, language, message):
    clara = by_name(repositories, sample_class["id"], "Clara Souza")
    repositories.students.deactivate(clara["id"])
    page = make_page()
    open_class_screen(page, repositories, sample_class, language)

    label = "Reactivate" if language == "en" else "Reativar"
    find_button(transferred_card(page, "Clara Souza"), label).on_click(None)

    assert repositories.students.get(clara["id"])["active"] is True
    assert student_card(page, "Clara Souza") is not None  # back in the active list
    assert "Transferred" not in screen_text(page) and "transferidos" not in screen_text(page)
    assert " ".join(collect_texts(page.dialog.content)) == message


def test_reactivate_failure_shows_an_error_message(
    make_page, repositories, sample_class, database
):
    repositories.students.deactivate(by_name(repositories, sample_class["id"], "Clara Souza")["id"])
    page = make_page()
    open_class_screen(page, repositories, sample_class)
    reactivate = find_button(transferred_card(page, "Clara Souza"), "Reactivate")
    database.close()  # storage failure

    reactivate.on_click(None)

    message = page.dialog
    assert isinstance(message, ft.SnackBar) and message.bgcolor == ft.Colors.ERROR
    assert "Couldn't reactivate the student. Please try again." in collect_texts(message.content)


def test_class_with_only_transferred_students(make_page, repositories):
    class_data = repositories.classes.add("Preschool III")
    gael = repositories.students.add(class_data["id"], "Gael Lima")
    repositories.students.deactivate(gael["id"])
    page = make_page()

    open_class_screen(page, repositories, class_data)

    text = screen_text(page)
    assert "No students yet" in text
    assert "Transferred students (1)" in text
    assert layout(page)[1] is None  # no "Add event" without active children


def test_remove_student_cancel_keeps_the_student(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    menu_item(page, "Davi Santos", "Remove from class").on_click(None)
    page.dialog.actions[0].on_click(None)  # cancel

    assert "Davi Santos" in screen_text(page)


def test_remove_student_shows_an_error_when_it_fails(
    make_page, repositories, sample_class, database
):
    page = make_page()
    open_class_screen(page, repositories, sample_class)
    menu_item(page, "Luna Costa", "Remove from class").on_click(None)
    database.close()  # simulate a storage failure

    page.dialog.actions[1].on_click(None)

    assert "Couldn't remove the student. Please try again." in collect_texts(page.dialog)


# --- child screen (learning story) --------------------------------------------------------


def test_tapping_a_child_opens_their_story(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    student_card(page, "Luna Costa").on_click(None)

    text = screen_text(page)
    assert "Learning story" in text
    assert "No events yet" in text
    assert "build Luna Costa's learning story" in text
    assert find_button(layout(page)[1], "Add event") is not None

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)  # back
    assert "Add student" in screen_text(page)


def test_story_shows_events_newest_first_with_photos_and_other_children(
    make_page, repositories, sample_class
):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    bento = by_name(repositories, sample_class["id"], "Bento Oliveira")
    repositories.events.add(sample_class["id"], [alice["id"]], "Older: first drawing",
                            date(2024, 3, 1), [PNG])
    repositories.events.add(sample_class["id"], [alice["id"], bento["id"]],
                            "Newer: built a tower together", date(2024, 5, 10), [JPEG, PNG])
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)

    app.open_child(alice)

    text = screen_text(page)
    assert text.index("Newer: built a tower together") < text.index("Older: first drawing")
    assert "05/10/2024" in text and "03/01/2024" in text
    assert "With Bento Oliveira" in text
    images = find_all(page.controls[-1], lambda c: isinstance(c, ft.Image))
    assert [image.src for image in images] == [JPEG, PNG, PNG]  # decrypted in memory


def story_event_bodies(page):
    """The body (under the date) of each event card of the story."""
    cards = find_all(
        page.controls[-1],
        lambda c: isinstance(c, ft.Container)
        and isinstance(c.content, ft.Column)
        and c.content.controls
        and isinstance(c.content.controls[0], ft.Row)
        and any(isinstance(x, ft.Icon) and x.icon == ft.Icons.EVENT
                for x in c.content.controls[0].controls),
    )
    return [card.content.controls[1] for card in cards]


def test_event_text_goes_beside_the_photo_on_wide_screens_and_below_on_phones(
    make_page, repositories, sample_class
):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.events.add(
        sample_class["id"], [alice["id"]], "Photo and text", date.today(), [JPEG]
    )
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)

    app.open_child(alice)

    [body] = story_event_bodies(page)
    assert isinstance(body, ft.ResponsiveRow)
    photos, text = body.controls
    assert [i.src for i in find_all(photos, lambda c: isinstance(c, ft.Image))] == [JPEG]
    assert "Photo and text" in collect_texts(text)
    xs, sm = ft.ResponsiveRowBreakpoint.XS, ft.ResponsiveRowBreakpoint.SM
    # Phones (xs): 12 of 12 columns each -> the text goes below the photo.
    assert photos.col[xs] == 12 and text.col[xs] == 12
    # Tablets/computers (sm and up): side by side, photo on the left.
    assert photos.col[sm] + text.col[sm] == 12
    assert body.controls.index(photos) < body.controls.index(text)
    # The default breakpoint is 576 px: narrower than any tablet, wider than phones.
    assert body.breakpoints[sm] == 576
    assert photos.horizontal_alignment == ft.CrossAxisAlignment.STRETCH  # photo fills its side


def test_events_with_only_text_or_only_photos_use_the_full_width(
    make_page, repositories, sample_class
):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.events.add(sample_class["id"], [alice["id"]], "Only text", date(2024, 1, 2))
    repositories.events.add(sample_class["id"], [alice["id"]], "", date(2024, 1, 1), [PNG])
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)

    app.open_child(alice)

    only_text, only_photo = story_event_bodies(page)
    assert not isinstance(only_text, ft.ResponsiveRow) and "Only text" in collect_texts(only_text)
    assert not isinstance(only_photo, ft.ResponsiveRow)
    assert [i.src for i in find_all(only_photo, lambda c: isinstance(c, ft.Image))] == [PNG]


def test_story_shows_ten_events_at_a_time(make_page, repositories, sample_class):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    for day in range(1, 13):
        repositories.events.add(sample_class["id"], [alice["id"]], f"Moment {day:02d}",
                                date(2024, 1, day))
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.open_child(alice)

    assert "Moment 12" in screen_text(page)
    assert "Moment 02" not in screen_text(page)
    find_button(page.controls[-1], "Show older events").on_click(None)

    assert "Moment 01" in screen_text(page)
    assert find_button(page.controls[-1], "Show older events") is None


# --- events ---------------------------------------------------------------------------------


def event_form(page):
    """Named parts of the open event form."""
    body, bottom_bar = layout(page)
    root = body.controls[0]
    fields = find_all(root, lambda c: isinstance(c, ft.TextField))
    return SimpleNamespace(
        description=fields[0],
        date=fields[1],
        chips={collect_texts(c)[0]: c for c in find_all(root, lambda c: isinstance(c, ft.Chip))},
        gallery=find_button(root, "Gallery"),
        take_photo=find_button(root, "Take photo"),
        thumbnails=find_all(root, lambda c: isinstance(c, ft.Image)),
        error=find_all(root, lambda c: isinstance(c, ft.Text) and c.color == ft.Colors.ERROR)[0],
        save=find_button(bottom_bar, "Save event") or find_button(bottom_bar, "Salvar evento"),
        root=root,
    )


def type_description(form, text):
    form.description.value = text
    form.description.on_change(SimpleNamespace(control=form.description))


def icon_button(page, tooltip):
    return find_all(
        page.controls[-1], lambda c: isinstance(c, ft.IconButton) and c.tooltip == tooltip
    )[0]


def test_add_event_from_the_class_screen(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    find_button(layout(page)[1], "Add event").on_click(None)
    form = event_form(page)
    asyncio.run(form.gallery.on_click(None))  # the fake gallery returns one photo
    form = event_form(page)
    assert len(form.thumbnails) == 1
    type_description(form, "Built a tower with 10 blocks and counted them.")
    pick_date(page, form.date, date(2024, 5, 10))
    form.chips["Alice Martins"].on_select(None)
    form.chips["Bento Oliveira"].on_select(None)
    form.save.on_click(None)

    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    bento = by_name(repositories, sample_class["id"], "Bento Oliveira")
    [event] = repositories.events.story(alice["id"])
    assert event["description"] == "Built a tower with 10 blocks and counted them."
    assert event["occurred_on"] == date(2024, 5, 10)
    assert sorted(event["student_ids"]) == sorted([alice["id"], bento["id"]])
    assert repositories.events.load_photo(event["photo_ids"][0]) == JPEG
    assert repositories.events.story(bento["id"]) == [event]
    # Back on the class screen, with the counts updated.
    assert "Add student" in screen_text(page)
    assert "1 event" in collect_texts(student_card(page, "Alice Martins"))


def test_add_event_from_a_childs_story_preselects_the_child(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.open_child(by_name(repositories, sample_class["id"], "Clara Souza"))

    find_button(layout(page)[1], "Add event").on_click(None)
    form = event_form(page)
    clara = form.chips["Clara Souza"]
    assert clara.selected is True
    assert not any(c.selected for name, c in form.chips.items() if name != "Clara Souza")
    # Easy to see: listed first, highlighted, and named under the title.
    assert list(form.chips)[0] == "Clara Souza"
    assert clara.selected_color == COLORS["primary"] and clara.label.color == ft.Colors.WHITE
    assert form.chips["Alice Martins"].label.color == COLORS["ink"]
    assert "New event | Clara Souza" in screen_text(page)
    type_description(form, "Said her first full sentence.")
    form.save.on_click(None)

    # Back on Clara's story, showing the new event.
    text = screen_text(page)
    assert "Learning story" in text
    assert "Said her first full sentence." in text


def test_add_event_from_the_class_screen_starts_with_no_child_selected(
    make_page, repositories, sample_class
):
    page = make_page()
    open_class_screen(page, repositories, sample_class)

    find_button(layout(page)[1], "Add event").on_click(None)

    form = event_form(page)
    assert not any(chip.selected for chip in form.chips.values())
    assert list(form.chips)[0] == "Alice Martins"  # alphabetical
    assert f"New event | {sample_class['name']}" in screen_text(page)


def test_tapping_a_child_toggles_the_highlight(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class).start_event()
    chip = event_form(page).chips["Bento Oliveira"]

    chip.on_select(None)
    assert chip.selected and chip.label.color == ft.Colors.WHITE
    chip.on_select(None)
    assert not chip.selected and chip.label.color == COLORS["ink"]


@pytest.mark.parametrize(
    ("language", "label", "old_label"),
    [("pt", "Alunos neste evento", "Crianças neste evento"),
     ("en", "Students in this event", "Children in this event")],
)
def test_students_section_label(make_page, repositories, sample_class, language, label, old_label):
    page = make_page()
    open_class_screen(page, repositories, sample_class, language).start_event()

    assert label in screen_text(page)
    assert old_label not in screen_text(page)


def saved_message(page):
    """Text of the information message shown after saving (or None)."""
    message = page.dialog
    if not isinstance(message, ft.SnackBar):
        return None
    icons = find_all(message.content, lambda c: isinstance(c, ft.Icon))
    assert icons and icons[0].icon == ft.Icons.INFO_OUTLINE  # an information message
    return " ".join(collect_texts(message.content))


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Event saved to the learning stories of 2 students."),
        ("pt", "Evento salvo nas histórias de aprendizagem de 2 alunos."),
    ],
)
def test_saving_an_event_shows_an_information_message(
    make_page, repositories, sample_class, language, expected
):
    page = make_page()
    open_class_screen(page, repositories, sample_class, language).start_event()
    form = event_form(page)
    form.chips["Alice Martins"].on_select(None)
    form.chips["Bento Oliveira"].on_select(None)
    type_description(form, "Shared the blocks")

    form.save.on_click(None)

    assert saved_message(page) == expected
    assert page.dialog.duration == ft.Duration(seconds=4)  # disappears by itself
    assert event_form_is_closed(page)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Event saved to Clara Souza's learning story."),
        ("pt", "Evento salvo na história de aprendizagem de Clara Souza."),
    ],
)
def test_saving_an_event_for_one_child_names_the_child(
    make_page, repositories, sample_class, language, expected
):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, language)
    app.open_child(by_name(repositories, sample_class["id"], "Clara Souza"))
    add_event = "Add event" if language == "en" else "Adicionar evento"
    find_button(layout(page)[1], add_event).on_click(None)
    type_description(event_form(page), "First full sentence")

    event_form(page).save.on_click(None)

    assert saved_message(page) == expected
    assert "First full sentence" in screen_text(page)  # back on Clara's story


def test_no_saved_message_when_the_event_is_not_saved(
    make_page, repositories, sample_class, database
):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.start_event()
    form = event_form(page)

    form.save.on_click(None)  # validation error: no child selected
    assert saved_message(page) is None

    form.chips["Alice Martins"].on_select(None)
    type_description(form, "x")
    database.close()  # storage failure
    form.save.on_click(None)
    assert saved_message(page) is None
    assert form.error.value == "Couldn't save the event. Please try again."


def event_form_is_closed(page):
    return find_button(page.controls[-1], "Save event") is None and \
        find_button(page.controls[-1], "Salvar evento") is None


def test_whole_class_is_the_last_option_and_selects_every_child(
    make_page, repositories, sample_class
):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.start_event()
    form = event_form(page)
    texts = screen_text(page)
    assert "Select all" not in texts and "Clear" not in texts  # removed
    assert list(form.chips)[-1] == "Whole class"  # after all the children
    assert not any(chip.selected for chip in form.chips.values())  # nothing preselected

    form.chips["Whole class"].on_select(None)

    kids = {name: chip for name, chip in form.chips.items() if name != "Whole class"}
    assert len(kids) == 5 and all(chip.selected for chip in kids.values())
    assert form.chips["Whole class"].selected
    assert form.chips["Whole class"].label.color == ft.Colors.WHITE
    type_description(form, "Class trip to the park")
    form.save.on_click(None)
    counts = repositories.events.count_by_student()
    assert all(counts[s["id"]] == 1 for s in repositories.students.list_active(sample_class["id"]))


@pytest.mark.parametrize(("language", "label"), [("en", "Whole class"), ("pt", "Turma")])
def test_whole_class_label(make_page, repositories, sample_class, language, label):
    page = make_page()
    open_class_screen(page, repositories, sample_class, language).start_event()

    assert list(event_form(page).chips)[-1] == label
    assert "Selecionar todas" not in screen_text(page) and "Limpar" not in screen_text(page)


def test_whole_class_follows_the_individual_selection(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class).start_event()
    form = event_form(page)
    kids = [chip for name, chip in form.chips.items() if name != "Whole class"]

    for chip in kids:  # the teacher selects every child one by one
        chip.on_select(None)
    assert form.chips["Whole class"].selected

    kids[0].on_select(None)  # one child unselected: not the whole class anymore
    assert not form.chips["Whole class"].selected

    form.chips["Whole class"].on_select(None)  # adds the missing child back
    assert all(chip.selected for chip in kids)
    form.chips["Whole class"].on_select(None)  # tapped again when all are selected: clears
    assert not any(chip.selected for chip in kids)


def test_whole_class_from_a_childs_story(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.open_child(by_name(repositories, sample_class["id"], "Clara Souza"))
    app.start_event(preselected=by_name(repositories, sample_class["id"], "Clara Souza")["id"])
    form = event_form(page)
    assert not form.chips["Whole class"].selected  # only Clara so far

    form.chips["Whole class"].on_select(None)

    assert all(chip.selected for chip in form.chips.values())


def test_event_form_fields_use_the_full_width(make_page, repositories, sample_class):
    page = make_page()
    open_class_screen(page, repositories, sample_class).start_event()
    form = event_form(page)

    column = form.root.controls[1].content  # the form fields (below the header)
    assert column.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert form.description in column.controls  # stretched by the column
    assert form.date in column.controls
    assert form.description.label == "What happened?"


@pytest.mark.parametrize(
    ("language", "setup", "message"),
    [
        ("en", "nothing", "Select at least one child."),
        ("pt", "nothing", "Selecione pelo menos uma criança."),
        ("en", "child_only", "Add a photo or describe what happened."),
        ("pt", "child_only", "Adicione uma foto ou descreva o que aconteceu."),
    ],
)
def test_event_validation_messages(make_page, repositories, sample_class, language, setup, message):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, language)
    app.start_event()
    form = event_form(page)
    if setup == "child_only":
        next(iter(form.chips.values())).on_select(None)

    button_label = "Save event" if language == "en" else "Salvar evento"
    find_button(layout(page)[1], button_label).on_click(None)

    assert form.error.value == message and form.error.visible
    assert repositories.events.count_by_student() == {}


def test_remove_a_photo_before_saving(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, gallery=FakeGallery([JPEG, PNG]))
    app.start_event()
    asyncio.run(event_form(page).gallery.on_click(None))
    assert len(event_form(page).thumbnails) == 2

    remove = find_all(event_form(page).root,
                      lambda c: isinstance(c, ft.IconButton) and c.tooltip == "Remove photo")
    remove[0].on_click(None)

    assert [t.src for t in event_form(page).thumbnails] == [PNG]


def test_gallery_failure_shows_a_message(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class, gallery=FakeGallery(fails=True))
    app.start_event()

    asyncio.run(event_form(page).gallery.on_click(None))

    assert event_form(page).error.value == "Couldn't open the gallery. Please try again."


def test_cancel_an_empty_event_goes_straight_back(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.start_event()

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)

    assert page.dialog is None
    assert "Add student" in screen_text(page)


def test_cancel_an_event_with_content_asks_before_discarding(make_page, repositories, sample_class):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    app.start_event()
    asyncio.run(event_form(page).gallery.on_click(None))
    back = find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0]

    back.on_click(None)
    assert page.dialog.title.value == "Discard this event?"
    page.dialog.actions[0].on_click(None)  # keep editing
    assert len(event_form(page).thumbnails) == 1

    back.on_click(None)
    page.dialog.actions[1].on_click(None)  # discard
    assert "Add student" in screen_text(page)
    assert app.draft is None
    assert repositories.events.count_by_student() == {}


CAMERA_HINT = "The camera isn't available on this device. Use the gallery to add photos."


@pytest.mark.parametrize(
    ("platform", "web", "camera"),
    [
        (ft.PagePlatform.ANDROID, False, True),
        (ft.PagePlatform.IOS, False, True),
        (ft.PagePlatform.MACOS, True, True),  # web app (any browser)
        (ft.PagePlatform.WINDOWS, False, False),  # desktop window (`flet run`)
        (ft.PagePlatform.MACOS, False, False),
        (ft.PagePlatform.LINUX, False, False),
    ],
)
def test_event_form_offers_take_photo_or_gallery(
    make_page, repositories, sample_class, platform, web, camera
):
    page = make_page()
    page.platform, page.web = platform, web
    open_class_screen(page, repositories, sample_class).start_event()

    form = event_form(page)
    assert form.take_photo is not None and form.gallery is not None
    options = find_all(
        form.root, lambda c: isinstance(c, ft.Row) and form.take_photo in c.controls
    )
    assert len(options) == 1 and form.gallery in options[0].controls  # side by side
    assert form.take_photo.expand and form.gallery.expand  # same width, full row
    # Where the camera can't work, "Take photo" is blocked and a message explains why.
    assert bool(form.take_photo.disabled) is (not camera)
    assert not form.gallery.disabled
    hint = find_all(form.root, lambda c: isinstance(c, ft.Row) and CAMERA_HINT in collect_texts(c))
    assert hint[-1].visible is (not camera)


def test_disabled_take_photo_button_looks_grey(make_page, repositories, sample_class):
    """A fixed color would hide the disabled look: the style must have a grey disabled state."""
    page = make_page()
    page.platform = ft.PagePlatform.WINDOWS
    open_class_screen(page, repositories, sample_class).start_event()
    form = event_form(page)

    take_photo, gallery = form.take_photo, form.gallery
    assert take_photo.disabled and not gallery.disabled
    style = take_photo.style
    for colors in (style.bgcolor, style.color, style.icon_color):
        assert isinstance(colors, dict), "colors must depend on the button state"
        assert colors[ft.ControlState.DISABLED] != colors[ft.ControlState.DEFAULT]
    assert style.bgcolor[ft.ControlState.DISABLED] == COLORS["disabled"]
    assert style.color[ft.ControlState.DISABLED] == COLORS["disabled_text"]
    assert style.icon_color[ft.ControlState.DISABLED] == COLORS["disabled_text"]
    assert style.bgcolor[ft.ControlState.DEFAULT] == COLORS["mint"]  # enabled look unchanged

    # Flet sends the per-state colors to the phone with the button.
    take_photo.before_update()
    assert take_photo._internals["style"].bgcolor == style.bgcolor


def test_camera_screen_is_never_opened_where_the_camera_is_unsupported(
    make_page, repositories, sample_class
):
    """Desktop: "Take photo" must not crash the app (flet-camera raises there)."""
    page = make_page()
    page.platform = ft.PagePlatform.WINDOWS
    app = open_class_screen(page, repositories, sample_class)
    app.start_event()
    type_description(event_form(page), "Kept while trying the camera")

    app.open_camera()  # even if the button were tapped somehow

    form = event_form(page)
    assert form.save is not None  # still on the form, no camera screen
    assert page.tasks == []  # the camera was never started
    assert form.error.value == CAMERA_HINT and form.error.visible
    assert form.description.value == "Kept while trying the camera"


def test_camera_refusing_to_start_returns_to_the_form(make_page, repositories, sample_class):
    """Safety net: if flet-camera rejects the platform anyway, show a message instead."""

    def unsupported_camera():
        raise ft.FletUnsupportedPlatformException(
            "Camera is currently only supported on Android, iOS and Web platforms."
        )

    page = make_page()
    page.platform = ft.PagePlatform.ANDROID
    app = KidNotesApp(page, repositories, "en", gallery=FakeGallery(),
                      camera_factory=unsupported_camera)
    app.open_class(sample_class)
    app.start_event()

    event_form(page).take_photo.on_click(None)

    form = event_form(page)
    assert form.save is not None
    assert form.error.value == CAMERA_HINT


@pytest.mark.parametrize("platform", list(ft.PagePlatform))
@pytest.mark.parametrize("web", [False, True])
def test_camera_rule_matches_flet_camera(platform, web, monkeypatch):
    """`camera_supported` must agree with flet-camera's own platform check."""
    from flet.controls.base_control import BaseControl

    from media import camera_supported

    fake_page = SimpleNamespace(platform=platform, web=web)
    monkeypatch.setattr(BaseControl, "page", property(lambda self: fake_page))
    monkeypatch.setattr(ft.LayoutControl, "before_update", lambda self: None)
    camera = fc.Camera()
    try:
        camera.before_update()
        flet_camera_allows = True
    except ft.FletUnsupportedPlatformException:
        flet_camera_allows = False

    assert camera_supported(fake_page) is flet_camera_allows


@pytest.mark.parametrize("screen", ["class", "event_form"])
def test_bottom_action_bar_button_uses_the_full_width(
    make_page, repositories, sample_class, screen
):
    page = make_page()
    app = open_class_screen(page, repositories, sample_class)
    if screen == "child":
        app.open_child(by_name(repositories, sample_class["id"], "Alice Martins"))
    elif screen == "event_form":
        app.start_event()

    bar = layout(page)[1]
    # `expand` only stretches the button inside a Row (not directly in a Container).
    assert isinstance(bar.content, ft.Row)
    [button] = bar.content.controls
    assert isinstance(button, ft.FilledButton) and button.expand is True


def test_take_photo_with_the_camera(make_page, repositories, sample_class):
    camera = FakeCamera(photo=PNG)
    page = make_page()
    page.platform = ft.PagePlatform.IOS
    app = open_class_screen(page, repositories, sample_class, camera=camera)
    app.start_event()
    form = event_form(page)
    type_description(form, "Painting with fingers")
    form.chips["Luna Costa"].on_select(None)

    form.take_photo.on_click(None)
    handler, _ = page.tasks[-1]  # the app starts the camera after showing the screen
    asyncio.run(handler())
    assert camera.initialized_with == ("back", fc.ResolutionPreset.VERY_HIGH, False)
    shutter = find_all(page.controls[-1],
                       lambda c: isinstance(c, ft.IconButton) and c.tooltip == "Take photo")[0]
    assert shutter.disabled is False
    asyncio.run(shutter.on_click(None))

    # Back on the form: the draft kept the text and the selected child.
    form = event_form(page)
    assert [t.src for t in form.thumbnails] == [PNG]
    assert form.description.value == "Painting with fingers"
    assert form.chips["Luna Costa"].selected
    form.save.on_click(None)
    luna = by_name(repositories, sample_class["id"], "Luna Costa")
    [event] = repositories.events.story(luna["id"])
    assert repositories.events.load_photo(event["photo_ids"][0]) == PNG


def test_camera_unavailable_shows_a_message(make_page, repositories, sample_class):
    page = make_page()
    page.platform = ft.PagePlatform.ANDROID
    app = open_class_screen(page, repositories, sample_class,
                            camera=FakeCamera(available=False))
    app.start_event()
    event_form(page).take_photo.on_click(None)

    asyncio.run(page.tasks[-1][0]())

    assert "The camera is not available." in screen_text(page)
    shutter = find_all(page.controls[-1],
                       lambda c: isinstance(c, ft.IconButton) and c.tooltip == "Take photo")[0]
    assert shutter.disabled is True
    icon_button(page, "Close").on_click(None)
    assert event_form(page).save is not None  # back on the form


# --- startup ----------------------------------------------------------------------------------


def class_card(page, name):
    """The clickable card of class `name` on the home screen."""
    cards = find_all(
        page.controls[-1],
        lambda c: isinstance(c, ft.Container) and c.on_click and name in collect_texts(c),
    )
    assert len(cards) == 1, f"card of {name!r} not found"
    return cards[0]


def test_app_reopens_the_last_chosen_class(make_page):
    """Create a class, open it, add a student, restart and sign in: the class screen opens."""
    page = make_page([ft.Locale("en")])
    asyncio.run(main.main(page))
    sign_up(page)
    find_button(page.controls[-1], "Add new class").on_click(None)
    name_field, save_button, _ = class_form_parts(page)
    name_field.value = "Preschool I"
    save_button.on_click(None)
    class_card(page, "Preschool I").on_click(None)
    icon_button(page, "Add student").on_click(None)
    student_name, _, student_save, _ = student_form_parts(page)
    student_name.value = "Alice Martins"
    student_save.on_click(None)

    restarted = make_page([ft.Locale("en")])
    asyncio.run(main.main(restarted))
    assert "Sign in to open your classes." in screen_text(restarted)  # login required
    sign_in(restarted)

    text = screen_text(restarted)
    assert "Preschool I" in text
    assert "Alice Martins" in text
    assert "Add event" in text


def test_choosing_another_class_changes_the_start_screen(make_page, repositories, sample_class):
    other = repositories.classes.add("Preschool II")
    page = make_page()
    app = start(page, repositories)
    app.open_class(sample_class)
    app.navigate("classes")
    class_card(page, "Preschool II").on_click(None)

    restarted = make_page()
    start(restarted, repositories)

    assert other["name"] in screen_text(restarted)
    assert "Add student" in screen_text(restarted)


def test_app_starts_on_home_when_no_class_was_chosen(make_page, repositories, sample_class):
    page = make_page()
    start(page, repositories)

    assert "Your classes" in screen_text(page)


def test_app_starts_on_home_when_the_last_class_no_longer_exists(make_page, repositories):
    repositories.settings.set_last_class_id("deleted-class-id")
    page = make_page()

    start(page, repositories)

    assert "Your classes" in screen_text(page)


def test_startup_shows_an_error_when_the_key_is_missing(make_page, app_storage):
    asyncio.run(main.main(make_page([ft.Locale("en")])))
    (app_storage / "dev-database.key").unlink()

    page = make_page([ft.Locale("en")])
    asyncio.run(main.main(page))

    assert "Your data can't be opened" in screen_text(page)
    assert (app_storage / "accounts.db").exists()  # nothing was deleted


# --- sign in / create account ------------------------------------------------------------


def start_root(page):
    from database.bootstrap import open_account_store

    accounts = asyncio.run(open_account_store())
    return AppRoot(page, accounts, "en", gallery=FakeGallery(), camera_factory=FakeCamera)


def auth_error(page):
    errors = find_all(
        page.controls[-1],
        lambda c: isinstance(c, ft.Text) and c.color == ft.Colors.ERROR and c.visible,
    )
    return errors[0].value if errors else None


def test_first_use_shows_account_creation_with_the_password_notice(make_page):
    page = make_page()
    start_root(page)

    text = screen_text(page)
    assert "Create your account to start." in text
    assert "A forgotten password can't be recovered" in text
    fields = auth_fields(page)
    assert set(fields) == {"Email", "Password", "Confirm password"}
    assert fields["Password"].password and fields["Password"].can_reveal_password
    assert fields["Confirm password"].password
    assert fields["Email"].keyboard_type == ft.KeyboardType.EMAIL


@pytest.mark.parametrize(
    ("email", "password", "confirmation", "message"),
    [
        ("not-an-email", "secret-pass", "secret-pass", "Enter a valid email address."),
        ("ana@school.org", "short", "short", "The password must have at least 8 characters."),
        ("ana@school.org", "secret-pass", "secret-pasS", "The passwords don't match."),
    ],
)
def test_registration_validation(make_page, email, password, confirmation, message):
    page = make_page()
    root = start_root(page)
    fields = auth_fields(page)
    fill(fields["Email"], email)
    fill(fields["Password"], password)
    fill(fields["Confirm password"], confirmation)

    find_button(page.controls[-1], "Create account").on_click(None)

    assert auth_error(page) == message
    assert root.session is None
    assert not root.accounts.has_accounts()


def test_registration_messages_in_portuguese(make_page):
    from database.bootstrap import open_account_store

    page = make_page()
    AppRoot(page, asyncio.run(open_account_store()), "pt", gallery=FakeGallery())
    fields = auth_fields(page)
    fill(fields["E-mail"], "ana")
    find_button(page.controls[-1], "Criar conta").on_click(None)

    assert auth_error(page) == "Informe um e-mail válido."


def test_sign_in_after_registration_and_wrong_password(make_page):
    page = make_page()
    start_root(page)
    sign_up(page, "Ana@School.org ")  # normalized: trimmed, lowercase
    assert "ana@school.org" in screen_text(page)  # the signed-in teacher on the home

    restarted = make_page()
    root = start_root(restarted)
    assert "Sign in to open your classes." in screen_text(restarted)
    sign_in(restarted, "ana@school.org", "wrong-password")
    assert auth_error(restarted) == "Email or password is incorrect."
    assert root.session is None

    sign_in(restarted, "nobody@school.org", "secret-pass")  # same message: no hint
    assert auth_error(restarted) == "Email or password is incorrect."

    sign_in(restarted, "ANA@school.org", "secret-pass")
    assert root.session is not None
    assert "Your classes" in screen_text(restarted)


def test_switch_between_sign_in_and_create_account(make_page):
    page = make_page()
    start_root(page)
    sign_up(page)
    root = start_root(make_page())
    page = root.page

    find_button(page.controls[-1], "Don't have an account? Create one").on_click(None)
    assert "Create your account to start." in screen_text(page)
    find_button(page.controls[-1], "Already have an account? Sign in").on_click(None)
    assert "Sign in to open your classes." in screen_text(page)


def test_email_can_only_be_registered_once(make_page):
    page = make_page()
    start_root(page)
    sign_up(page)
    page = make_page()
    start_root(page)
    find_button(page.controls[-1], "Don't have an account? Create one").on_click(None)

    sign_up(page, "ana@school.org", "another-pass")

    assert auth_error(page) == "There is already an account with this email on this device."


def test_sign_out_closes_the_teachers_data(make_page):
    page = make_page()
    root = start_root(page)
    sign_up(page)
    session = root.session

    find_button(page.controls[-1], "Sign out").on_click(None)

    assert root.session is None and root.app is None
    assert "Sign in to open your classes." in screen_text(page)
    with pytest.raises(Exception):  # the database connection was closed
        session.database.get("classes", "x")


def test_each_teacher_only_sees_their_own_classes(make_page):
    page = make_page()
    start_root(page)
    sign_up(page, "ana@school.org")
    find_button(page.controls[-1], "Add new class").on_click(None)
    name_field, save_button, _ = class_form_parts(page)
    name_field.value = "Ana's class"
    save_button.on_click(None)
    find_button(page.controls[-1], "Sign out").on_click(None)

    find_button(page.controls[-1], "Don't have an account? Create one").on_click(None)
    sign_up(page, "bia@school.org", "bia-password")

    assert "bia@school.org" in screen_text(page)
    assert "Ana's class" not in screen_text(page)
    assert "No classes yet" in screen_text(page)


# --- editing events ---------------------------------------------------------------------


def open_story_with_event(page, repositories, sample_class, photos=(JPEG, PNG)):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    bento = by_name(repositories, sample_class["id"], "Bento Oliveira")
    event = repositories.events.add(
        sample_class["id"], [alice["id"], bento["id"]], "Built a tower",
        date(2024, 5, 10), list(photos),
    )
    app = open_class_screen(page, repositories, sample_class)
    app.open_child(alice)
    return app, event, alice, bento


def edit_button(page):
    buttons = find_all(page.controls[-1],
                       lambda c: isinstance(c, ft.IconButton) and c.tooltip == "Edit event")
    return buttons


def test_each_event_in_the_story_has_an_edit_button(make_page, repositories, sample_class):
    page = make_page()
    open_story_with_event(page, repositories, sample_class)

    assert len(edit_button(page)) == 1


def test_edit_an_event(make_page, repositories, sample_class):
    page = make_page()
    app, event, alice, bento = open_story_with_event(page, repositories, sample_class)
    old_photo_files = set(event["photo_ids"])

    edit_button(page)[0].on_click(None)
    form = event_form(page)
    assert "Edit event | Alice Martins" in screen_text(page)
    assert form.description.value == "Built a tower"
    assert form.date.value == "05/10/2024"
    assert form.chips["Alice Martins"].selected and form.chips["Bento Oliveira"].selected
    assert [t.src for t in form.thumbnails] == [JPEG, PNG]  # decrypted saved photos

    type_description(form, "Built a tower with 12 blocks")
    pick_date(page, form.date, date(2024, 5, 11))
    form.chips["Bento Oliveira"].on_select(None)  # unlink Bento
    form.chips["Clara Souza"].on_select(None)  # link Clara
    find_all(form.root, lambda c: isinstance(c, ft.IconButton)
             and c.tooltip == "Remove photo")[0].on_click(None)  # remove the JPEG
    asyncio.run(event_form(page).gallery.on_click(None))  # add a new photo (JPEG)
    event_form(page).save.on_click(None)

    updated = repositories.events.get(event["id"])
    clara = by_name(repositories, sample_class["id"], "Clara Souza")
    assert updated["description"] == "Built a tower with 12 blocks"
    assert updated["occurred_on"] == date(2024, 5, 11)
    assert sorted(updated["student_ids"]) == sorted([alice["id"], clara["id"]])
    assert [repositories.events.load_photo(p) for p in updated["photo_ids"]] == [PNG, JPEG]
    assert repositories.events.story(bento["id"]) == []
    # The removed photo's encrypted file was deleted; the kept one was not re-saved.
    assert event["photo_ids"][1] in updated["photo_ids"]
    assert event["photo_ids"][0] not in updated["photo_ids"]
    assert repositories.events.load_photo(event["photo_ids"][0]) is None
    assert len(old_photo_files & set(updated["photo_ids"])) == 1
    # Back on the story with a message, and no duplicate event.
    assert " ".join(collect_texts(page.dialog.content)) == "Event updated."
    assert screen_text(page).count("Built a tower with 12 blocks") == 1
    assert len(repositories.events.story(alice["id"])) == 1


def test_edit_an_event_in_portuguese(make_page, repositories, sample_class):
    page = make_page()
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.events.add(sample_class["id"], [alice["id"]], "Pintou", date(2024, 5, 10))
    app = open_class_screen(page, repositories, sample_class, "pt")
    app.open_child(alice)

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
             and c.tooltip == "Editar evento")[0].on_click(None)
    assert "Editar evento | Alice Martins" in screen_text(page)
    event_form(page).save.on_click(None)

    assert " ".join(collect_texts(page.dialog.content)) == "Evento atualizado."


def test_edit_keeps_a_transferred_child_linked(make_page, repositories, sample_class):
    page = make_page()
    app, event, alice, bento = open_story_with_event(page, repositories, sample_class)
    repositories.students.deactivate(bento["id"])
    app.render()

    edit_button(page)[0].on_click(None)
    form = event_form(page)
    assert form.chips["Bento Oliveira"].selected  # still shown, as he is linked
    type_description(form, "Edited after Bento left")
    form.save.on_click(None)

    assert bento["id"] in repositories.events.get(event["id"])["student_ids"]


def test_cancel_edit_without_changes_goes_straight_back(make_page, repositories, sample_class):
    page = make_page()
    app, event, *_ = open_story_with_event(page, repositories, sample_class)
    edit_button(page)[0].on_click(None)

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)

    assert page.dialog is None
    assert "Learning story" in screen_text(page)


def test_cancel_edit_with_changes_asks_first(make_page, repositories, sample_class):
    page = make_page()
    app, event, *_ = open_story_with_event(page, repositories, sample_class)
    edit_button(page)[0].on_click(None)
    type_description(event_form(page), "Not saved")

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)
    assert page.dialog.title.value == "Discard changes?"
    page.dialog.actions[1].on_click(None)  # discard

    assert repositories.events.get(event["id"])["description"] == "Built a tower"
    assert "Learning story" in screen_text(page)


def test_edit_validation_still_applies(make_page, repositories, sample_class):
    page = make_page()
    open_story_with_event(page, repositories, sample_class, photos=())
    edit_button(page)[0].on_click(None)
    form = event_form(page)

    find_all(form.root, lambda c: isinstance(c, ft.Chip)
             and "Whole class" in collect_texts(c))[0].on_select(None)  # select all
    find_all(form.root, lambda c: isinstance(c, ft.Chip)
             and "Whole class" in collect_texts(c))[0].on_select(None)  # clear all
    form.save.on_click(None)

    assert form.error.value == "Select at least one child."


# --- home header / add student button ---------------------------------------------------


def test_home_header_has_no_avatar_circle(make_page):
    page = make_page()
    start_root(page)
    sign_up(page, "ana@school.org")

    texts = collect_texts(page.controls[-1])
    assert "ana@school.org" in texts  # the teacher is still shown
    assert "A" not in texts  # no circle with the email's first letter
    assert find_button(page.controls[-1], "Sign out") is not None


@pytest.mark.parametrize(("language", "tooltip"), [("en", "Add student"),
                                                   ("pt", "Adicionar aluno")])
def test_add_student_is_an_icon_only_button(make_page, repositories, sample_class,
                                            language, tooltip):
    page = make_page()
    open_class_screen(page, repositories, sample_class, language)

    [button] = find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
                        and c.tooltip == tooltip)
    assert button.icon == ft.Icons.PERSON_ADD_ALT_1
    assert isinstance(button, ft.OutlinedIconButton)
    assert getattr(button, "content", None) is None  # no text, only the icon
    assert find_button(page.controls[-1], tooltip) is None  # no button with that text


# --- extra information about the child ---------------------------------------------------


def open_child_screen(page, repositories, sample_class, name="Clara Souza", language="en"):
    app = open_class_screen(page, repositories, sample_class, language)
    app.open_child(by_name(repositories, sample_class["id"], name))
    return app


def extra_info_card(page):
    """The card with the saved extra information on the child screen (or None)."""
    cards = find_all(page.controls[-1], lambda c: isinstance(c, ft.Container)
                     and c.data == "extra-info")
    if not cards:
        return None
    card = cards[0]
    card.text = card.content.controls[-1].value  # the saved notes
    return card


@pytest.mark.parametrize(
    ("language", "extra", "add"),
    [("en", "Extra information", "Add event"),
     ("pt", "Informações extras", "Adicionar evento")],
)
def test_extra_information_is_next_to_add_event(
    make_page, repositories, sample_class, language, extra, add
):
    page = make_page()
    open_child_screen(page, repositories, sample_class, language=language)

    body, bottom_bar = layout(page)
    row = bottom_bar.content
    assert isinstance(row, ft.Row) and len(row.controls) == 2
    left, right = row.controls
    # Side by side in the fixed bottom bar: extra information | add event.
    assert find_button(left, extra) is left and find_button(right, add) is right
    assert left.expand and right.expand  # same width, the whole bar
    assert right.style.bgcolor == COLORS["primary"]  # "Add event" is the main action
    assert left.style.bgcolor != COLORS["primary"]
    # Icon above the label, one line: fits two buttons on a phone.
    for button in (left, right):
        icon, label = button.content.controls
        assert isinstance(icon, ft.Icon) and label.max_lines == 1
    # Not at the top anymore.
    assert find_button(body, extra) is None
    assert not extra_info_card(page).visible  # nothing written yet


def extra_info_screen(page):
    """(text area, save button, back button) of the extra information screen."""
    body, bottom_bar = layout(page)
    [area] = find_all(body, lambda c: isinstance(c, ft.TextField))
    back = find_all(body, lambda c: isinstance(c, ft.IconButton))[0]
    save = find_button(bottom_bar, "Save") or find_button(bottom_bar, "Salvar")
    return area, save, back


def write(area, text):
    area.value = text
    area.on_change(SimpleNamespace(control=area))


def test_extra_information_is_a_screen(make_page, repositories, sample_class):
    page = make_page()
    open_child_screen(page, repositories, sample_class)

    find_button(layout(page)[1], "Extra information").on_click(None)

    assert page.dialog is None  # a screen, not a dialog
    text = screen_text(page)
    assert "Extra information | Clara Souza" in text  # header: title + child
    assert "Likes, habits and other things worth knowing about Clara Souza." in text
    area, save, back = extra_info_screen(page)
    assert area.multiline and area.min_lines >= 12  # a big writing area
    column = find_all(page.controls[-1], lambda c: isinstance(c, ft.Column) and area in c.controls)
    assert column[0].horizontal_alignment == ft.CrossAxisAlignment.STRETCH  # full width
    assert save is not None  # full-width save button in the bottom bar
    assert "Learning story" not in text


def test_write_extra_information(make_page, repositories, sample_class):
    page = make_page()
    app = open_child_screen(page, repositories, sample_class)
    clara = by_name(repositories, sample_class["id"], "Clara Souza")

    find_button(layout(page)[1], "Extra information").on_click(None)
    area, save, _ = extra_info_screen(page)
    write(area, "She loves sleeping after lunch.\nShe plays football with one friend.")
    save.on_click(None)

    saved = repositories.students.get(clara["id"])["notes"]
    assert saved == "She loves sleeping after lunch.\nShe plays football with one friend."
    # Back on the child screen, with the text and a message.
    assert "Learning story" in screen_text(page)
    assert " ".join(collect_texts(page.dialog.content)) == "Extra information saved."
    card = extra_info_card(page)
    assert card.visible and card.text == saved
    assert app.selected_student["notes"] == saved

    # Opening it again shows the saved text; clearing it hides the card.
    find_button(layout(page)[1], "Extra information").on_click(None)
    area, save, _ = extra_info_screen(page)
    assert area.value == saved
    write(area, "   ")
    save.on_click(None)
    assert repositories.students.get(clara["id"])["notes"] == ""
    assert not extra_info_card(page).visible


def test_extra_information_back_without_changes(make_page, repositories, sample_class):
    page = make_page()
    open_child_screen(page, repositories, sample_class)
    find_button(layout(page)[1], "Extra information").on_click(None)

    extra_info_screen(page)[2].on_click(None)

    assert page.dialog is None
    assert "Learning story" in screen_text(page)


def test_extra_information_back_with_changes_asks_first(make_page, repositories, sample_class):
    page = make_page()
    open_child_screen(page, repositories, sample_class)
    clara = by_name(repositories, sample_class["id"], "Clara Souza")
    find_button(layout(page)[1], "Extra information").on_click(None)
    area, _, back = extra_info_screen(page)
    write(area, "Not saved yet")

    back.on_click(None)
    assert page.dialog.title.value == "Discard changes?"
    assert "The text you wrote won't be saved." in collect_texts(page.dialog)
    page.dialog.actions[0].on_click(None)  # keep editing
    assert extra_info_screen(page)[0].value == "Not saved yet"

    back.on_click(None)
    page.dialog.actions[1].on_click(None)  # discard
    assert "Learning story" in screen_text(page)
    assert repositories.students.get(clara["id"])["notes"] == ""


def test_extra_information_text_survives_a_rebuild(make_page, repositories, sample_class):
    page = make_page()
    app = open_child_screen(page, repositories, sample_class)
    find_button(layout(page)[1], "Extra information").on_click(None)
    write(extra_info_screen(page)[0], "Half-written note")

    app.render()  # e.g. the device language changed

    assert extra_info_screen(page)[0].value == "Half-written note"


def test_extra_information_errors(make_page, repositories, sample_class, database):
    page = make_page()
    open_child_screen(page, repositories, sample_class)
    find_button(layout(page)[1], "Extra information").on_click(None)
    area, save, _ = extra_info_screen(page)

    write(area, "x" * 4001)
    save.on_click(None)
    assert area.error == "The text is too long."

    write(area, "ok")
    assert area.error is None  # cleared while typing
    database.close()  # storage failure
    save.on_click(None)
    assert area.error == "Couldn't save. Please try again."
    assert "Extra information | Clara Souza" in screen_text(page)  # still on the screen


def test_extra_information_in_portuguese(make_page, repositories, sample_class):
    page = make_page()
    open_child_screen(page, repositories, sample_class, language="pt")

    find_button(layout(page)[1], "Informações extras").on_click(None)
    assert "Informações extras | Clara Souza" in screen_text(page)
    area, save, _ = extra_info_screen(page)
    assert area.hint_text == "Ex.: Ela adora dormir depois do almoço."
    write(area, "Ele adora jogar futebol com um amigo.")
    save.on_click(None)

    assert " ".join(collect_texts(page.dialog.content)) == "Informações extras salvas."
    assert extra_info_card(page).text == "Ele adora jogar futebol com um amigo."


def test_extra_information_is_per_child(make_page, repositories, sample_class):
    clara = by_name(repositories, sample_class["id"], "Clara Souza")
    repositories.students.update_notes(clara["id"], "Clara's note")
    page = make_page()

    open_child_screen(page, repositories, sample_class, "Luna Costa")

    assert "Clara's note" not in screen_text(page)
    assert not extra_info_card(page).visible


# --- sign-in screen remembers the email --------------------------------------------------


def test_sign_in_screen_comes_with_the_last_email(make_page):
    page = make_page()
    start_root(page)
    sign_up(page, "ana@school.org")

    restarted = make_page()
    start_root(restarted)

    fields = auth_fields(restarted)
    assert fields["Email"].value == "ana@school.org"
    assert fields["Password"].value in (None, "")
    assert fields["Password"].autofocus and not fields["Email"].autofocus  # type the password
    fill(fields["Password"], "secret-pass")
    find_button(restarted.controls[-1], "Sign in").on_click(None)
    assert "Your classes" in screen_text(restarted)


def test_after_sign_out_the_email_stays_filled(make_page):
    page = make_page()
    start_root(page)
    sign_up(page, "bia@school.org")

    find_button(page.controls[-1], "Sign out").on_click(None)

    assert auth_fields(page)["Email"].value == "bia@school.org"
    find_button(page.controls[-1], "Don't have an account? Create one").on_click(None)
    assert auth_fields(page)["Email"].value in (None, "")  # a new account starts empty


# --- regression: the reports button from the real start-up path ---------------------------


def test_reports_button_through_the_full_app(make_page):
    """Sign up → class → 📄: the path that failed with "'Repositories' object has no
    attribute 'reports'" when old and new code were mixed."""
    page = make_page([ft.Locale("pt", "BR")])
    asyncio.run(main.main(page))
    fields = auth_fields(page)
    fill(fields["E-mail"], "ana@school.org")
    fill(fields["Senha"], "secret-pass")
    fill(fields["Confirme a senha"], "secret-pass")
    find_button(page.controls[-1], "Criar conta").on_click(None)
    find_button(page.controls[-1], "Adicionar nova turma").on_click(None)
    name_field, save_button, _ = class_form_parts(page)
    name_field.value = "Maternal I"
    save_button.on_click(None)
    class_card(page, "Maternal I").on_click(None)

    icon_button(page, "Relatórios").on_click(None)

    assert "Relatórios | Maternal I" in screen_text(page)


def test_every_repository_used_by_the_app_exists():
    """`app.py` and `database/repositories.py` must agree (catches a missing repository)."""
    import re
    from pathlib import Path

    from database import Repositories

    used = set(re.findall(r"self\.repos\.(\w+)", (Path(__file__).parent.parent / "app.py")
                          .read_text(encoding="utf-8")))
    fields = set(Repositories.__dataclass_fields__)
    assert used and used <= fields, f"missing in Repositories: {used - fields}"
