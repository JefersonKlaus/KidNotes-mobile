"""Tests for reports: pseudonymization, prompt, Groq client, PDF, storage and screens."""

import asyncio
import io
import json
from datetime import date, timedelta
from types import SimpleNamespace

import flet as ft
import httpx
import pytest
from pypdf import PdfReader

from i18n import Translator
from reports.ai import GROQ_MODEL, GROQ_URL, GroqClient, ReportAIError
from reports.document import build_report_pdf, report_filename
from reports.generate import events_in_period, write_report
from reports.prompt import PLACEHOLDER, Pseudonymizer, build_prompt, clean_answer
from tests.conftest import JPEG, collect_texts, find_all, find_button, screen_text
from tests.test_app import by_name, layout, open_class_screen, pick_date

TODAY = date.today()


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


# --- pseudonymization --------------------------------------------------------------------


def test_names_are_replaced_before_sending():
    names = Pseudonymizer("Clara Souza", ["Bento Oliveira", "Álvaro Lima"], "um(a) colega")

    hidden = names.hide(
        "Clara Souza pintou com tinta clara. CLARA riu com Bento e o Alvaro; Bentoso não."
    )

    assert hidden == (
        "[NOME] pintou com tinta clara. [NOME] riu com um(a) colega e o um(a) colega; "
        "Bentoso não."
    )


def test_the_childs_first_name_is_put_back():
    names = Pseudonymizer("Clara Souza", [], "a classmate")
    assert names.restore("[NOME] sings. [nome] dances. [ Nome ] reads.") == (
        "Clara sings. Clara dances. Clara reads."
    )


def test_clean_answer_removes_markdown():
    answer = "# Relatório\n\n**[NOME]** brincou.\n- com blocos\n\n\n\nPróximos   passos."
    assert clean_answer(answer) == (
        "Relatório\n\n[NOME] brincou.\n\ncom blocos\n\nPróximos passos."
    )


# --- prompt ------------------------------------------------------------------------------


def student(**extra):
    return {"id": "s1", "name": "Clara Souza", "birth_date": date(2021, 3, 10),
            "notes": "Clara adora dormir depois do almoço e brinca com o Bento.", **extra}


def event(day, description, children=1, photos=0):
    return {"occurred_on": day, "description": description,
            "student_ids": [f"s{i}" for i in range(1, children + 1)],
            "photo_ids": [f"{i:032x}" for i in range(photos)]}


def test_prompt_contents_and_privacy():
    tr = Translator("pt")
    events = [
        event(date(2025, 5, 2), "Clara contou os blocos com o Bento.", children=2, photos=1),
        event(date(2025, 3, 1), "Clara pintou o sol."),
        event(date(2025, 4, 1), "", photos=2),  # photo only
    ]

    system, user, _ = build_prompt(tr, student(), events, date(2025, 2, 1), date(2025, 6, 30),
                                   ["Bento Oliveira"])

    assert "BNCC" in system and "[NOME]" in system and "Não invente" in system
    assert "Período: 01/02/2025 a 30/06/2025" in user
    assert "Idade da criança no fim do período: 4 anos" in user  # age, not the birth date
    assert user.index("01/03/2025: [NOME] pintou o sol.") < user.index("02/05/2025")
    assert "02/05/2025: [NOME] contou os blocos com o um(a) colega. (com 1 colega(s))" in user
    assert "[NOME] adora dormir depois do almoço" in user
    assert "1 registro(s) somente com foto" in user
    for private in ("Clara", "Souza", "Bento", "2021", "10/03", "0" * 32):
        assert private not in user, private


def test_prompt_in_english():
    events = [event(date(2025, 3, 1), "Painted")]
    system, user, _ = build_prompt(Translator("en"), student(notes=""), events,
                                   date(2025, 2, 1), date(2025, 6, 30), [])
    assert "early childhood" in system
    assert "Period: 02/01/2025 to 06/30/2025" in user
    assert "03/01/2025: Painted" in user


def test_events_in_period_includes_both_ends():
    events = [event(date(2025, 1, 31), "a"), event(date(2025, 2, 1), "b"),
              event(date(2025, 6, 30), "c"), event(date(2025, 7, 1), "d")]
    assert [e["description"] for e in events_in_period(events, date(2025, 2, 1),
                                                       date(2025, 6, 30))] == ["b", "c"]


class FakeAI:
    """Stands in for the Groq client: records prompts, answers with the placeholder."""

    model = "fake-model"

    def __init__(self, key="key", fail_with=None, answer=None):
        self.key = key
        self.fail_with = fail_with or {}
        self.answer = answer
        self.calls = []

    async def complete(self, system, user):
        self.calls.append((system, user))
        code = self.fail_with.get(len(self.calls))
        if code:
            raise ReportAIError(code)
        default = f"**{PLACEHOLDER}** teve um período de descobertas.\n\n- Próximos passos."
        return self.answer or default


def test_write_report_restores_the_name_on_the_device():
    ai = FakeAI()
    text = asyncio.run(write_report(ai, Translator("pt"), student(), [event(TODAY, "Clara leu.")],
                                    TODAY, TODAY, ["Bento Oliveira"]))

    assert text == "Clara teve um período de descobertas.\n\nPróximos passos."
    assert "Clara" not in ai.calls[0][1]


# --- Groq client ------------------------------------------------------------------------


def groq(handler, key="gsk_test"):
    return GroqClient(key, transport=httpx.MockTransport(handler))


def test_groq_request_and_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Texto"}}]})

    assert asyncio.run(groq(handler).complete("sys", "user")) == "Texto"
    assert seen["url"] == GROQ_URL
    assert seen["auth"] == "Bearer gsk_test"
    assert seen["body"]["model"] == GROQ_MODEL
    assert seen["body"]["messages"] == [{"role": "system", "content": "sys"},
                                        {"role": "user", "content": "user"}]


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={}), "invalid_key"),
        (httpx.Response(403, json={}), "invalid_key"),
        (httpx.Response(429, json={}), "rate_limited"),
        (httpx.Response(500, json={}), "service"),
        (httpx.Response(200, text="not json"), "service"),
        (httpx.Response(200, json={"choices": []}), "service"),
        (httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}), "empty"),
    ],
)
def test_groq_errors(response, code):
    with pytest.raises(ReportAIError) as error:
        asyncio.run(groq(lambda _: response).complete("s", "u"))
    assert error.value.code == code


@pytest.mark.parametrize(
    ("exception", "code"),
    [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("offline"), "network")],
)
def test_groq_connection_problems(exception, code):
    def handler(request):
        raise exception

    with pytest.raises(ReportAIError) as error:
        asyncio.run(groq(handler).complete("s", "u"))
    assert error.value.code == code


def test_groq_without_a_key_sends_nothing():
    calls = []
    with pytest.raises(ReportAIError) as error:
        asyncio.run(groq(lambda r: calls.append(r), key="").complete("s", "u"))
    assert error.value.code == "missing_key" and calls == []


# --- PDF ------------------------------------------------------------------------------------


def report(text="Primeiro parágrafo.\n\nSegundo parágrafo com ação e emoção ❤."):
    return {"period_start": date(2025, 2, 1), "period_end": date(2025, 6, 30), "text": text}


def test_report_pdf_contents():
    pdf = build_report_pdf(Translator("pt"), student(), "Maternal I - Manhã", report(),
                           issued_on=date(2025, 7, 1))

    assert pdf.startswith(b"%PDF-1.4")
    reader = PdfReader(io.BytesIO(pdf))
    assert reader.metadata.title == "Relatório de desenvolvimento e aprendizagem - Clara Souza"
    text = pdf_text(pdf)
    for expected in ("Relatório de desenvolvimento e aprendizagem", "Clara Souza",
                     "Turma: Maternal I - Manhã", "Idade: 4 anos",
                     "Período: 01/02/2025 a 30/06/2025", "Emitido em 01/07/2025",
                     "Primeiro parágrafo.", "Segundo parágrafo com ação e emoção",
                     "Professor(a)", "Página 1 de 1"):
        assert expected in text, expected
    assert "?" not in text  # the emoji was dropped, not replaced


def test_long_reports_get_more_pages():
    long_text = "\n\n".join(f"Parágrafo {i}: " + "descoberta " * 60 for i in range(12))

    pdf = build_report_pdf(Translator("en"), student(birth_date=None), "Class", report(long_text))

    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 3
    assert f"Page {len(reader.pages)} of {len(reader.pages)}" in reader.pages[-1].extract_text()
    assert "Parágrafo 11" in pdf_text(pdf)


def test_pdf_renders(tmp_path):
    pdfium = pytest.importorskip("pypdfium2")
    pdf = build_report_pdf(Translator("pt"), student(), "Turma", report())
    page = pdfium.PdfDocument(pdf)[0]
    image = page.render(scale=1).to_pil()
    assert image.size[0] > 500 and image.getextrema() != ((255, 255), (255, 255), (255, 255))


def test_report_filename():
    assert report_filename({"name": "Álvaro D'Ávila"}, report()) == (
        "relatorio-alvaro-d-avila-2025-02-01-2025-06-30.pdf"
    )


# --- storage ---------------------------------------------------------------------------------


def test_reports_are_stored_encrypted(repositories, sample_class, database):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    first = repositories.reports.add(sample_class["id"], alice["id"], date(2025, 2, 1),
                                     date(2025, 6, 30), "Texto secreto sobre a Alice", 3, "m")
    second = repositories.reports.add(sample_class["id"], alice["id"], date(2025, 2, 1),
                                      date(2025, 6, 30), "Outro", 3, "m")

    assert [r["id"] for r in repositories.reports.list_for_class(sample_class["id"])] == [
        second["id"], first["id"]]
    edited = repositories.reports.update_text(first["id"], "Texto revisado")
    assert repositories.reports.get(first["id"])["text"] == "Texto revisado" == edited["text"]
    raw = b"".join(f.read_bytes() for f in database.path.parent.rglob("*") if f.is_file())
    assert b"Texto" not in raw and b"revisado" not in raw


def test_api_key_is_stored_encrypted(repositories, database):
    assert repositories.settings.get_groq_api_key() is None
    repositories.settings.set_groq_api_key("  gsk_secret_123  ")

    assert repositories.settings.get_groq_api_key() == "gsk_secret_123"
    raw = b"".join(f.read_bytes() for f in database.path.parent.rglob("*") if f.is_file())
    assert b"gsk_secret" not in raw


# --- screens ---------------------------------------------------------------------------------


def text_fields(page):
    found = find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
    return {f.label: f for f in found}


class FakeExporter:
    def __init__(self, saved=True):
        self.saved = saved
        self.calls = []

    async def save(self, data, filename):
        self.calls.append(("save", data, filename))
        return self.saved

    async def share(self, data, filename):
        self.calls.append(("share", data, filename))


def open_reports(page, repositories, sample_class, ai=None, exporter=None, language="en",
                 key="gsk_test"):
    if key:
        repositories.settings.set_groq_api_key(key)
    app = open_class_screen(page, repositories, sample_class, language)
    app.ai_client_factory = lambda k: ai or FakeAI(k)
    app.exporter = exporter or FakeExporter()
    icon = find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
                    and c.tooltip == ("Reports" if language == "en" else "Relatórios"))
    icon[0].on_click(None)
    return app


def report_chips(page):
    return {collect_texts(c)[0]: c for c in find_all(page.controls[-1],
                                                   lambda c: isinstance(c, ft.Chip))}


def generate(page):
    bar = layout(page)[1]
    button = find_button(bar, "Generate reports") or find_button(bar, "Gerar relatórios")
    asyncio.run(button.on_click(None))


def add_events(repositories, sample_class):
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    bento = by_name(repositories, sample_class["id"], "Bento Oliveira")
    repositories.events.add(sample_class["id"], [alice["id"], bento["id"]],
                            "Alice e Bento construíram uma torre.", TODAY - timedelta(days=3),
                            [JPEG])
    repositories.events.add(sample_class["id"], [alice["id"]], "Alice contou até dez.",
                            TODAY - timedelta(days=1))
    repositories.events.add(sample_class["id"], [alice["id"]], "Muito antiga.",
                            TODAY - timedelta(days=400))
    return alice, bento


@pytest.mark.parametrize(("language", "tooltip", "title"),
                         [("en", "Reports", "Reports"), ("pt", "Relatórios", "Relatórios")])
def test_class_screen_has_a_reports_button(make_page, repositories, sample_class,
                                           language, tooltip, title):
    page = make_page()
    open_reports(page, repositories, sample_class, language=language)

    assert f"{title} | {sample_class['name']}" in screen_text(page)


def test_report_screen_defaults(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class)

    fields = text_fields(page)
    app_tr = Translator("en")
    assert fields["From"].value == app_tr.format_date(TODAY - timedelta(days=182))
    assert fields["To"].value == app_tr.format_date(TODAY)
    chips = report_chips(page)
    assert "Alice Martins (2)" in chips  # the 400-day-old event is out of the period
    assert "Bento Oliveira (1)" in chips and "Clara Souza (0)" in chips
    assert list(chips)[-1] == "Whole class"
    assert "Names are replaced before sending and photos are never sent." in screen_text(page)
    assert "Groq API key configured" in screen_text(page)
    assert "No reports yet." in screen_text(page)


def test_changing_the_period_updates_the_counts(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class)
    fields = text_fields(page)

    pick_date(page, fields["From"], TODAY - timedelta(days=500))

    assert "Alice Martins (3)" in report_chips(page)


def test_api_key_is_asked_for_and_saved(make_page, repositories, sample_class, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    page = make_page()
    open_reports(page, repositories, sample_class, key=None)
    [key_field] = [f for f in find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
                   if f.label == "Groq API key"]
    assert key_field.password

    find_button(page.controls[-1], "Save key").on_click(None)
    assert key_field.error == "Paste the API key."
    key_field.value = "gsk_new"
    find_button(page.controls[-1], "Save key").on_click(None)

    assert repositories.settings.get_groq_api_key() == "gsk_new"
    assert "Groq API key configured" in screen_text(page)
    find_button(page.controls[-1], "Change").on_click(None)
    assert find_button(page.controls[-1], "Save key") is not None


def test_generate_one_report_per_selected_student(make_page, repositories, sample_class):
    alice, bento = add_events(repositories, sample_class)
    ai = FakeAI()
    page = make_page()
    open_reports(page, repositories, sample_class, ai=ai)
    chips = report_chips(page)
    chips["Alice Martins (2)"].on_select(None)
    chips["Bento Oliveira (1)"].on_select(None)
    chips["Clara Souza (0)"].on_select(None)

    generate(page)

    assert len(ai.calls) == 2  # Clara has no events: nothing sent for her
    sent = " ".join(user for _, user in ai.calls)
    for private in ("Alice", "Bento", "Martins", "Oliveira", sample_class["name"]):
        assert private not in sent, private
    assert "Muito antiga" not in sent  # out of the period
    reports = repositories.reports.list_for_class(sample_class["id"])
    assert sorted(r["student_id"] for r in reports) == sorted([alice["id"], bento["id"]])
    assert {r["text"] for r in reports} == {
        "Alice teve um período de descobertas.\n\nPróximos passos.",
        "Bento teve um período de descobertas.\n\nPróximos passos.",
    }
    text = screen_text(page)
    assert text.count("Report ready") == 2
    assert "No events in this period" in text
    assert "Generated reports" in text and text.count("generated on") == 2


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("nothing", "Select at least one student."),
        ("bad_period", "The start date must be before the end date."),
        ("no_key", "Add your Groq API key first."),
    ],
)
def test_generate_validation(make_page, repositories, sample_class, monkeypatch, setup, message):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    add_events(repositories, sample_class)
    ai = FakeAI()
    page = make_page()
    app = open_reports(page, repositories, sample_class, ai=ai,
                       key=None if setup == "no_key" else "gsk")
    if setup != "nothing":
        report_chips(page)["Alice Martins (2)"].on_select(None)
    if setup == "bad_period":
        app.set_report_period(TODAY, TODAY - timedelta(days=1))

    generate(page)

    assert message in screen_text(page)
    assert ai.calls == []


def test_ai_errors_are_shown_per_student(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    ai = FakeAI(fail_with={1: "rate_limited"})
    page = make_page()
    open_reports(page, repositories, sample_class, ai=ai)
    report_chips(page)["Whole class"].on_select(None)

    generate(page)

    text = screen_text(page)
    assert "Too many requests. Wait a minute and try again." in text  # Alice
    assert "Report ready" in text  # Bento: the next one still ran
    assert len(ai.calls) == 2


def test_invalid_key_stops_and_marks_everyone(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    ai = FakeAI(fail_with={1: "invalid_key"})
    page = make_page()
    open_reports(page, repositories, sample_class, ai=ai)
    report_chips(page)["Alice Martins (2)"].on_select(None)
    report_chips(page)["Bento Oliveira (1)"].on_select(None)

    generate(page)

    assert len(ai.calls) == 1
    assert screen_text(page).count("Invalid API key.") == 2


def test_generate_button_is_disabled_while_running(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    seen = {}
    page = make_page()

    class SpyAI(FakeAI):
        async def complete(self, system, user):
            bar = layout(page)[1]
            seen["disabled"] = bar.content.controls[0].disabled
            seen["status"] = "Writing the report..." in screen_text(page)
            return await super().complete(system, user)

    open_reports(page, repositories, sample_class, ai=SpyAI())
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)

    assert seen == {"disabled": True, "status": True}
    assert not layout(page)[1].content.controls[0].disabled  # enabled again at the end


def review_after_generating(page, repositories, sample_class, exporter=None):
    add_events(repositories, sample_class)
    app = open_reports(page, repositories, sample_class, exporter=exporter)
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)
    find_button(page.controls[-1], "Open").on_click(None)
    return app


def review_area(page):
    [area] = find_all(layout(page)[0], lambda c: isinstance(c, ft.TextField))
    return area


def test_review_edit_and_save_pdf(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    review_after_generating(page, repositories, sample_class, exporter)
    text = screen_text(page)
    assert "Report | Alice Martins" in text
    assert "Draft written by AI from your records." in text
    area = review_area(page)
    assert area.value.startswith("Alice teve um período de descobertas.")
    assert find_button(layout(page)[1], "Share PDF") is None  # desktop: save only

    area.value = "Alice cresceu muito neste semestre.\n\nContinuaremos com histórias."
    area.on_change(SimpleNamespace(control=area))
    asyncio.run(find_button(layout(page)[1], "Save PDF").on_click(None))

    [(kind, data, filename)] = exporter.calls
    assert kind == "save" and filename.startswith("relatorio-alice-martins-")
    assert "Alice cresceu muito neste semestre." in pdf_text(data)
    assert " ".join(collect_texts(page.dialog.content)) == "PDF saved."
    [saved] = repositories.reports.list_for_class(sample_class["id"])
    assert saved["text"].startswith("Alice cresceu muito")  # the edit was saved


def test_share_pdf_on_phones(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    page.platform = ft.PagePlatform.ANDROID
    review_after_generating(page, repositories, sample_class, exporter)

    bar = layout(page)[1]
    save, share = bar.content.controls
    assert find_button(save, "Save PDF") is save and find_button(share, "Share PDF") is share
    asyncio.run(share.on_click(None))

    [(kind, data, filename)] = exporter.calls
    assert kind == "share" and data.startswith(b"%PDF") and filename.endswith(".pdf")


def test_review_back_with_changes_asks_first(make_page, repositories, sample_class):
    page = make_page()
    review_after_generating(page, repositories, sample_class)
    area = review_area(page)
    area.value = "Mudado"
    area.on_change(SimpleNamespace(control=area))

    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)
    assert page.dialog.title.value == "Discard changes?"
    page.dialog.actions[1].on_click(None)  # discard

    assert "Generate reports" in screen_text(page)
    [saved] = repositories.reports.list_for_class(sample_class["id"])
    assert saved["text"] != "Mudado"


def test_empty_report_is_not_exported(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    review_after_generating(page, repositories, sample_class, exporter)
    area = review_area(page)
    area.value = "   "
    area.on_change(SimpleNamespace(control=area))

    asyncio.run(find_button(layout(page)[1], "Save PDF").on_click(None))

    assert exporter.calls == [] and area.error == "The report is empty."


def test_saved_reports_can_be_reopened(make_page, repositories, sample_class):
    page = make_page()
    review_after_generating(page, repositories, sample_class)
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)

    [row] = find_all(page.controls[-1], lambda c: isinstance(c, ft.Container)
                     and str(c.data).startswith("report:"))
    row.on_click(None)

    assert "Report | Alice Martins" in screen_text(page)


def test_report_screen_in_portuguese(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    text = screen_text(page)
    for expected in ("Período", "De", "Até", "Alunos", "Turma", "Gerar relatórios",
                     "Os nomes são trocados antes do envio", "Chave da API Groq configurada"):
        assert expected in text, expected
