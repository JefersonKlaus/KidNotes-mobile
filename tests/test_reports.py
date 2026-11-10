"""Tests for reports: pseudonymization, prompt, Groq client, PDF, storage and screens."""

import asyncio
import io
import json
import re
import zlib
from datetime import date, timedelta
from types import SimpleNamespace

import flet as ft
import httpx
import pytest
from pypdf import PdfReader

from i18n import Translator
from reports.ai import (
    GROQ_MODEL,
    GROQ_MODELS_URL,
    GROQ_URL,
    PREFERRED_MODELS,
    GroqClient,
    ReportAIError,
    choose_model,
)
from reports.document import build_report_pdf, report_filename
from reports.generate import events_in_period, write_report
from reports.prompt import (
    PLACEHOLDER,
    Pseudonymizer,
    build_prompt,
    clean_answer,
    ground_answer,
    is_title,
    max_paragraphs,
)
from tests.conftest import (
    JPEG,
    collect_texts,
    find_all,
    find_button,
    notice_is_error,
    notice_text,
    screen_text,
)
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
    assert "SOMENTE" in system and "será apagado" in system
    assert "Período: 01/02/2025 a 30/06/2025" in user
    assert "Idade da criança no fim do período: 4 anos" in user  # age, not the birth date
    # Numbered sources: the teacher's notes, then the records oldest first.
    assert "Fontes (3):" in user
    assert "[1] Informações da professora sobre a criança: [NOME] adora dormir" in user
    assert "[2] Registro de 01/03/2025: [NOME] pintou o sol." in user
    assert ("[3] Registro de 02/05/2025: [NOME] contou os blocos com o um(a) colega. "
            "(com 1 colega(s))") in user
    assert "no máximo 3 parágrafo(s)" in user  # 3 sources → a short report
    # Photo-only records are not mentioned: the AI can't see photos and would guess.
    assert "foto" not in user and "[4]" not in user
    for private in ("Clara", "Souza", "Bento", "2021", "10/03", "0" * 32):
        assert private not in user, private


def test_prompt_in_english():
    events = [event(date(2025, 3, 1), "Painted")]
    system, user, _ = build_prompt(Translator("en"), student(notes=""), events,
                                   date(2025, 2, 1), date(2025, 6, 30), [])
    assert "early childhood" in system and "ONLY" in system
    assert "Period: 02/01/2025 to 06/30/2025" in user
    assert "Sources (1):" in user and "[1] Record of 03/01/2025: Painted" in user
    assert "at most 2 paragraph(s)" in user


@pytest.mark.parametrize(("sources", "paragraphs"), [(1, 2), (2, 3), (3, 3), (5, 4), (20, 6)])
def test_few_records_ask_for_a_short_report(sources, paragraphs):
    assert max_paragraphs(sources) == paragraphs


# --- the answer must be based on the sources ---------------------------------------------


def test_paragraphs_without_a_source_are_removed():
    answer = ("[NOME] construiu uma torre com um(a) colega [2]. Depois contou até dez [3].\n\n"
              "[NOME] adora música e dança todos os dias.\n\n"
              "[NOME] gosta de pintar [9].\n\n"
              "Próximos passos: propor mais construções [2, 3].")

    result = ground_answer(answer, sources=3)

    assert result.text == (
        "[NOME] construiu uma torre com um(a) colega. Depois contou até dez.\n\n"
        "Próximos passos: propor mais construções."
    )
    assert result.kept == 2 and result.checked
    assert result.removed == ["[NOME] adora música e dança todos os dias.",
                              "[NOME] gosta de pintar."]
    assert result.unknown_sources == {9}  # cited a source that doesn't exist


@pytest.mark.parametrize("citation", ["[1][2]", "[1, 2]", "[1 e 2]", "[1 and 2]", "[ 1 ; 2 ]"])
def test_citation_formats(citation):
    result = ground_answer(f"[NOME] brincou {citation}.", sources=2)
    assert result.text == "[NOME] brincou." and result.kept == 1


def test_answer_without_any_citation_is_kept_but_flagged():
    result = ground_answer("[NOME] brincou.\n\nPróximos passos.", sources=2)
    assert result.text == "[NOME] brincou.\n\nPróximos passos."
    assert not result.checked


def test_invented_paragraphs_never_reach_the_report(caplog):
    caplog.set_level("INFO", logger="reports.generate")
    ai = FakeAI(answer="[NOME] pintou o sol [1].\n\n[NOME] andou de bicicleta no parque.")
    text = asyncio.run(write_report(ai, Translator("pt"), student(notes=""),
                                    [event(date(2025, 3, 1), "Clara pintou o sol.")],
                                    date(2025, 2, 1), date(2025, 6, 30), []))

    assert text == "Clara pintou o sol."
    assert "removed 1 paragraph(s) not based on the 1 source(s)" in caplog.text
    assert "bicicleta" not in caplog.text and "Clara" not in caplog.text  # counts/ids only


def test_an_answer_with_no_valid_source_is_rejected():
    ai = FakeAI(answer="[NOME] andou de bicicleta [7].")
    with pytest.raises(ReportAIError) as error:
        asyncio.run(write_report(ai, Translator("pt"), student(notes=""),
                                 [event(date(2025, 3, 1), "Clara pintou o sol.")],
                                 date(2025, 2, 1), date(2025, 6, 30), []))
    assert error.value.code == "ungrounded"


# --- the teacher's instructions (structure, standards...) --------------------------------


def test_instructions_go_to_the_prompt_with_names_hidden():
    events = [event(date(2025, 3, 1), "Clara pintou o sol.")]
    instructions = "Use as seções Interações e Linguagem. Não cite o Bento pelo nome."

    system, user, _ = build_prompt(Translator("pt"), student(notes=""), events,
                                   date(2025, 2, 1), date(2025, 6, 30), ["Bento Oliveira"],
                                   instructions)

    assert "ORIENTAÇÕES DA PROFESSORA" in system and "nunca o conteúdo" in system
    assert user.index("Fontes (1):") < user.index("Orientações da professora para o relatório")
    assert "não autorizam inventar" in user
    assert "Use as seções Interações e Linguagem. Não cite o um(a) colega pelo nome." in user
    assert "Bento" not in user


def test_no_instructions_section_when_empty():
    events = [event(date(2025, 3, 1), "Clara pintou o sol.")]
    _, user, _ = build_prompt(Translator("en"), student(notes=""), events,
                              date(2025, 2, 1), date(2025, 6, 30), [], "   ")
    assert "instructions" not in user


STRUCTURED_ANSWER = """## Interações
[NOME] brincou com um(a) colega [2].

**Linguagem:**
[NOME] contou até dez [3].

Corpo e movimento

Matemática
[NOME] contou blocos [3].

Próximos passos
Propor mais jogos de contagem [3]."""


def test_section_titles_are_kept_when_the_teacher_asked_for_a_structure():
    result = ground_answer(clean_answer(STRUCTURED_ANSWER), sources=3, allow_titles=True)

    assert result.text.split("\n\n") == [
        "Interações", "[NOME] brincou com um(a) colega.",
        "Linguagem:", "[NOME] contou até dez.",
        # "Corpo e movimento" had no text with sources: the empty section is dropped
        "Matemática", "[NOME] contou blocos.",
        "Próximos passos", "Propor mais jogos de contagem.",
    ]
    assert result.kept == 4  # titles are not counted as paragraphs


def test_without_instructions_titles_are_not_kept():
    result = ground_answer(clean_answer(STRUCTURED_ANSWER), sources=3)
    assert "Interações" not in result.text and "Matemática" not in result.text
    assert result.kept == 4


def test_invented_sentences_are_never_taken_for_titles():
    answer = "[NOME] pintou [1].\n\n[NOME] adora dançar e cantar com todos."
    result = ground_answer(answer, sources=1, allow_titles=True)
    assert result.text == "[NOME] pintou."  # it ends with "." → a sentence, removed
    assert not is_title("[NOME] adora dançar e cantar com todos.")


def test_a_sentence_broken_over_two_lines_stays_together():
    assert clean_answer("[NOME] construiu uma torre com\num(a) colega [1].") == (
        "[NOME] construiu uma torre com um(a) colega [1]."
    )


def test_write_report_sends_the_instructions_and_keeps_titles():
    ai = FakeAI(answer="Linguagem\n[NOME] pintou o sol [1].\n\nCorpo\n\nInventado sem fonte.")
    text = asyncio.run(write_report(ai, Translator("pt"), student(notes=""),
                                    [event(date(2025, 3, 1), "Clara pintou o sol.")],
                                    date(2025, 2, 1), date(2025, 6, 30), [],
                                    instructions="Seções: Linguagem e Corpo."))

    assert "Seções: Linguagem e Corpo." in ai.calls[0][1]
    assert text == "Linguagem\n\nClara pintou o sol."


def test_pdf_shows_section_titles():
    data = build_report_pdf(Translator("pt"), student(), "Turma",
                            report(text="Linguagem\n\nClara contou até dez."))
    text = pdf_text(data)
    assert "Linguagem" in text and "Clara contou até dez." in text
    streams = b"".join(zlib.decompress(m) for m in re.findall(
        rb"/FlateDecode >>\nstream\n(.*?)\nendstream", data, re.DOTALL))
    assert re.search(rb"/F2 12\.0 Tf [\d. ]+ Td \(Linguagem\) Tj", streams)  # bold title


def test_a_title_is_never_alone_at_the_bottom_of_a_page():
    from reports.pdf import PdfDocument

    doc = PdfDocument(title="t", footer="f")
    while doc.y > 120:  # fill the page until little room is left
        doc.text("linha", size=11)
    doc.text("Título", bold=True, keep_with_next=3 * 16.5)
    assert len(doc.pages) == 2 and doc.y > 600  # moved to the next page


def test_temperature_is_low():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    asyncio.run(groq(handler).complete("s", "u"))
    assert seen["temperature"] <= 0.2


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
        default = (f"**{PLACEHOLDER}** teve um período de descobertas. [1]\n\n"
                   "- Próximos passos. [1]")
        return self.answer or default


def test_write_report_restores_the_name_on_the_device():
    ai = FakeAI()
    text = asyncio.run(write_report(ai, Translator("pt"), student(), [event(TODAY, "Clara leu.")],
                                    TODAY, TODAY, ["Bento Oliveira"]))

    assert text == "Clara teve um período de descobertas.\n\nPróximos passos."
    assert "Clara" not in ai.calls[0][1]


# --- Groq client ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_model_override(monkeypatch):
    """A developer's GROQ_MODEL (.env) must not change what the tests expect."""
    monkeypatch.delenv("GROQ_MODEL", raising=False)


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


# --- Groq logs: enough to tell the key, the URL, the model or Groq itself apart ----------

SECRET_KEY = "gsk_abcdefghijklmnopqrstuvwxyz123456"
PRIVATE_PROMPT = "Alice Martins contou ate dez."


def run_logged(caplog, handler, key=SECRET_KEY):
    caplog.set_level("INFO", logger="reports.ai")
    with pytest.raises(ReportAIError) as error:
        asyncio.run(groq(handler, key=key).complete("system rules", PRIVATE_PROMPT))
    return error.value, caplog.text


def assert_nothing_private(log):
    assert SECRET_KEY not in log
    assert PRIVATE_PROMPT not in log and "system rules" not in log


def test_groq_error_message_is_logged(caplog):
    body = {"error": {"message": "Please reduce the length of the messages.",
                      "type": "invalid_request_error", "code": "context_length_exceeded"}}
    response = httpx.Response(400, json=body, headers={"x-request-id": "req_123"})

    error, log = run_logged(caplog, lambda _: response)

    assert error.code == "service"
    assert "HTTP 400" in error.detail and "context_length_exceeded" in error.detail
    assert "reduce the length" in log and "invalid_request_error" in log
    assert GROQ_URL in log and GROQ_MODEL in log and "req_123" in log
    assert "gsk_...3456" in log  # which key was used, masked
    assert_nothing_private(log)


def test_non_json_error_body_is_logged(caplog):
    error, log = run_logged(caplog, lambda _: httpx.Response(404, text="<html>Not Found</html>"))

    assert error.code == "service"
    assert "HTTP 404" in log and "<html>Not Found</html>" in log and GROQ_URL in log


def test_invalid_key_and_rate_limit_are_logged(caplog):
    error, log = run_logged(caplog, lambda _: httpx.Response(
        401, json={"error": {"message": "Invalid API Key", "code": "invalid_api_key"}}))
    assert error.code == "invalid_key" and "HTTP 401: Invalid API Key" in log
    caplog.clear()
    error, log = run_logged(caplog, lambda _: httpx.Response(
        429, json={"error": {"message": "Rate limit reached"}}, headers={"retry-after": "7"}))
    assert error.code == "rate_limited" and "Rate limit reached" in log
    assert "'retry-after': '7'" in log


def test_a_key_echoed_by_the_server_is_masked(caplog):
    _, log = run_logged(caplog, lambda _: httpx.Response(500, text=f"bad key {SECRET_KEY}"))
    assert "HTTP 500" in log
    assert_nothing_private(log)


def test_network_problem_is_logged(caplog):
    def handler(request):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    error, log = run_logged(caplog, handler)

    assert error.code == "network"
    assert "ConnectError" in log and "getaddrinfo failed" in log and GROQ_URL in log


def test_unexpected_answer_is_logged(caplog):
    error, log = run_logged(caplog, lambda _: httpx.Response(200, text="not json"))
    assert error.code == "service" and "unexpected answer format" in log and "not json" in log


# --- model not available for the key: ask Groq which models it can use ------------------

MODEL_NOT_FOUND = {"error": {
    "message": (
        "The model `llama-3.3-70b-versatile` does not exist or you do not have access to it."
    ),
    "type": "invalid_request_error", "code": "model_not_found"}}


def model_list(*ids):
    return {"object": "list", "data": [{"id": i, "object": "model", "active": True} for i in ids]}


class FakeGroq:
    """Mock Groq server: `allowed` models answer, the others give model_not_found."""

    def __init__(self, allowed, models_status=200):
        self.allowed = allowed
        self.models_status = models_status
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            assert str(request.url) == GROQ_MODELS_URL
            assert request.headers["Authorization"] == f"Bearer {SECRET_KEY}"
            if self.models_status != 200:
                return httpx.Response(self.models_status, json={"error": {"message": "nope"}})
            return httpx.Response(200, json=model_list(*self.allowed, "whisper-large-v3"))
        model = json.loads(request.content)["model"]
        if model not in self.allowed:
            return httpx.Response(404, json=MODEL_NOT_FOUND)
        return httpx.Response(200, json={"choices": [{"message": {"content": f"by {model}"}}]})

    def posted_models(self):
        return [json.loads(r.content)["model"] for r in self.requests if r.method == "POST"]


def test_unavailable_model_switches_to_an_available_one(caplog):
    caplog.set_level("INFO", logger="reports.ai")
    server = FakeGroq(allowed=["openai/gpt-oss-20b", "moonshotai/kimi-k2-instruct"])
    client = GroqClient(SECRET_KEY, transport=httpx.MockTransport(server))

    assert asyncio.run(client.complete("s", "u")) == "by moonshotai/kimi-k2-instruct"
    assert client.model == "moonshotai/kimi-k2-instruct"  # best one in PREFERRED_MODELS
    # The next student goes straight to the new model (no second model list).
    assert asyncio.run(client.complete("s", "u")) == "by moonshotai/kimi-k2-instruct"
    assert server.posted_models() == [GROQ_MODEL, "moonshotai/kimi-k2-instruct",
                                      "moonshotai/kimi-k2-instruct"]
    assert sum(r.method == "GET" for r in server.requests) == 1
    assert "models available for this key (3)" in caplog.text
    assert "switching to 'moonshotai/kimi-k2-instruct'" in caplog.text
    assert SECRET_KEY not in caplog.text


def test_no_usable_model_is_reported_with_the_available_list(caplog):
    caplog.set_level("INFO", logger="reports.ai")
    server = FakeGroq(allowed=["some/other-model"])
    with pytest.raises(ReportAIError) as error:
        asyncio.run(GroqClient(SECRET_KEY, transport=httpx.MockTransport(server))
                    .complete("s", "u"))

    assert error.value.code == "model"
    assert server.posted_models() == [GROQ_MODEL]  # nothing else was tried
    assert "some/other-model" in caplog.text and "set GROQ_MODEL" in caplog.text


def test_model_list_failure_gives_the_model_error(caplog):
    server = FakeGroq(allowed=["llama-3.1-8b-instant"], models_status=403)
    error, log = run_logged(caplog, server)
    assert error.code == "model" and "could not list the models: HTTP 403" in log


def test_a_refused_replacement_is_not_retried_forever():
    class Liar(FakeGroq):  # lists a model, then refuses it
        def __call__(self, request):
            if request.method == "POST":
                self.requests.append(request)
                return httpx.Response(404, json=MODEL_NOT_FOUND)
            return super().__call__(request)

    server = Liar(allowed=["openai/gpt-oss-20b"])
    with pytest.raises(ReportAIError) as error:
        asyncio.run(GroqClient(SECRET_KEY, transport=httpx.MockTransport(server))
                    .complete("s", "u"))
    assert error.value.code == "model"
    assert server.posted_models() == [GROQ_MODEL, "openai/gpt-oss-20b"]


def test_choose_model_follows_the_preference_order():
    assert choose_model(list(reversed(PREFERRED_MODELS)), set()) == PREFERRED_MODELS[0]
    assert choose_model(list(PREFERRED_MODELS), {PREFERRED_MODELS[0]}) == PREFERRED_MODELS[1]
    assert choose_model(["whisper-large-v3"], set()) is None
    assert choose_model(["llama-3.1-8b-instant"], set()) is None  # small models invent more


def test_groq_model_can_be_set_in_the_environment(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    asyncio.run(groq(handler).complete("s", "u"))
    assert seen["model"] == "openai/gpt-oss-120b"
    assert seen["reasoning_effort"] == "low"  # reasoning model: short "thinking"


def test_reasoning_is_removed_from_the_answer():
    assert clean_answer("<think>\nplanning...\n</think>\n\n[NOME] brincou.") == "[NOME] brincou."


def test_success_is_logged_without_the_text(caplog):
    caplog.set_level("INFO", logger="reports.ai")
    answer = {"choices": [{"message": {"content": "Texto do relatorio"},
                           "finish_reason": "stop"}],
              "usage": {"prompt_tokens": 11, "completion_tokens": 22}}
    text = asyncio.run(groq(lambda _: httpx.Response(200, json=answer), key=SECRET_KEY)
                       .complete("system rules", PRIVATE_PROMPT))

    assert text == "Texto do relatorio"
    assert "HTTP 200" in caplog.text and "finish_reason=stop" in caplog.text
    assert "prompt=11" in caplog.text and "completion=22" in caplog.text
    assert "Texto do relatorio" not in caplog.text
    assert_nothing_private(caplog.text)


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


def test_reports_can_be_deleted(repositories, sample_class, database):
    from database.reports import ReportNotFoundError

    add_events(repositories, sample_class)
    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    first = repositories.reports.add(sample_class["id"], alice["id"], date(2025, 2, 1),
                                     date(2025, 6, 30), "Um", 3, "m")
    second = repositories.reports.add(sample_class["id"], alice["id"], date(2025, 2, 1),
                                      date(2025, 6, 30), "Dois", 3, "m")
    events_before = repositories.events.story(alice["id"])

    repositories.reports.delete(first["id"])

    assert repositories.reports.get(first["id"]) is None
    assert [r["id"] for r in repositories.reports.list_for_class(sample_class["id"])] == [
        second["id"]]
    assert repositories.events.story(alice["id"]) == events_before  # the story is kept
    with pytest.raises(ReportNotFoundError):
        repositories.reports.delete(first["id"])
    assert database.delete("reports", "missing") is False
    with pytest.raises(ValueError):
        database.delete("not_a_table", "x")


def test_api_key_is_stored_encrypted(repositories, database):
    assert repositories.settings.get_groq_api_key() is None
    repositories.settings.set_groq_api_key("  gsk_secret_123  ")

    assert repositories.settings.get_groq_api_key() == "gsk_secret_123"
    raw = b"".join(f.read_bytes() for f in database.path.parent.rglob("*") if f.is_file())
    assert b"gsk_secret" not in raw


def test_report_instructions_are_stored_encrypted(repositories, database):
    assert repositories.settings.get_report_instructions() == ""
    repositories.settings.set_report_instructions("  Seções: Interações e Linguagem.  ")

    assert repositories.settings.get_report_instructions() == "Seções: Interações e Linguagem."
    raw = b"".join(f.read_bytes() for f in database.path.parent.rglob("*") if f.is_file())
    assert "Interações".encode() not in raw
    repositories.settings.set_report_instructions("x" * 5000)
    assert len(repositories.settings.get_report_instructions()) == 2000


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
    assert "Groq API key" not in screen_text(page)  # the key lives in Settings now
    assert "No reports yet." in screen_text(page)


def test_changing_the_period_updates_the_counts(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class)
    fields = text_fields(page)

    pick_date(page, fields["From"], TODAY - timedelta(days=500))

    assert "Alice Martins (3)" in report_chips(page)


def test_without_a_key_the_report_screen_points_to_settings(make_page, repositories,
                                                            sample_class, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    page = make_page()
    app = open_reports(page, repositories, sample_class, key=None)
    assert not [f for f in find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
                if f.label == "Groq API key"]  # no key field here anymore
    [notice] = find_all(page.controls[-1], lambda c: getattr(c, "data", None)
                        == "api-key-missing")
    assert "add your Groq API key in Settings" in " ".join(collect_texts(notice))

    find_button(notice, "Settings").on_click(None)
    assert app.route == "settings"
    fields = [f for f in find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))]
    [key_field] = [f for f in fields if f.label == "Groq API key"]
    key_field.value = "gsk_new"
    find_button(page.controls[-1], "Save key").on_click(None)
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)  # ←

    assert app.route == "reports"  # back where the teacher was
    assert not find_all(page.controls[-1], lambda c: getattr(c, "data", None)
                        == "api-key-missing")


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


def instructions_field(page):
    [field] = [f for f in find_all(page.controls[-1], lambda c: isinstance(c, ft.TextField))
               if f.hint_text and f.hint_text.startswith(("E.g.: Organize", "Ex.: Organize"))]
    return field


def type_instructions(field, text):
    field.value = text
    field.on_change(SimpleNamespace(control=field))


def test_instructions_field_is_saved_and_sent(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    ai = FakeAI()
    page = make_page()
    open_reports(page, repositories, sample_class, ai=ai)
    assert "Instructions for the report (optional)" in screen_text(page)
    field = instructions_field(page)
    assert field.value == "" and field.max_length == 2000

    type_instructions(field, "Sections: Interactions and Language.")
    field.on_blur(None)  # leaving the field saves it
    assert repositories.settings.get_report_instructions() == "Sections: Interactions and Language."

    type_instructions(instructions_field(page), "Sections: Play and Language.")
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)  # generating also saves it

    assert "Sections: Play and Language." in ai.calls[0][1]
    assert repositories.settings.get_report_instructions() == "Sections: Play and Language."
    assert instructions_field(page).value == "Sections: Play and Language."  # kept on re-render


def test_saved_instructions_come_back_next_time(make_page, repositories, sample_class):
    repositories.settings.set_report_instructions("Formal tone.")
    page = make_page()
    open_reports(page, repositories, sample_class)
    assert instructions_field(page).value == "Formal tone."


def test_instructions_screen_in_portuguese(make_page, repositories, sample_class):
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    assert "Orientações para o relatório (opcional)" in screen_text(page)
    assert "só com o que está nos seus registros" in instructions_field(page).helper


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("nothing", "Select at least one student."),
        ("bad_period", "The start date must be before the end date."),
        ("no_key", "Add your Groq API key in Settings."),
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


def test_unavailable_model_stops_and_is_explained(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    ai = FakeAI(fail_with={1: "model"})
    page = make_page()
    open_reports(page, repositories, sample_class, ai=ai)
    report_chips(page)["Alice Martins (2)"].on_select(None)
    report_chips(page)["Bento Oliveira (1)"].on_select(None)

    generate(page)

    assert len(ai.calls) == 1  # the same would happen for every student
    assert screen_text(page).count("The AI model is not available for this API key.") == 2


def test_failed_report_is_logged_with_the_reason(make_page, repositories, sample_class, caplog):
    caplog.set_level("INFO", logger="app")
    add_events(repositories, sample_class)

    class FailingAI(FakeAI):
        async def complete(self, system, user):
            raise ReportAIError("service", "HTTP 400: model decommissioned")

    page = make_page()
    open_reports(page, repositories, sample_class, ai=FailingAI())
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)

    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    assert "key from the key saved in the app" in caplog.text
    assert f"Report for student {alice['id']} failed: service" in caplog.text
    assert "HTTP 400: model decommissioned" in caplog.text
    assert "Alice" not in caplog.text  # ids only, no names


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


def review_buttons(page):
    """(Save text, Generate PDF): the two buttons of the review screen's bottom bar."""
    save, pdf = layout(page)[1].content.controls
    assert find_button(save, "Save text") is save and find_button(pdf, "Generate PDF") is pdf
    return save, pdf


def edit_review(page, text):
    area = review_area(page)
    area.value = text
    area.on_change(SimpleNamespace(control=area))
    return area


def test_review_edit_and_generate_pdf(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    review_after_generating(page, repositories, sample_class, exporter)
    text = screen_text(page)
    assert "Report | Alice Martins" in text
    assert "Draft written by AI from your records." in text
    assert review_area(page).value.startswith("Alice teve um período de descobertas.")
    _, pdf = review_buttons(page)
    share = find_all(page.controls[-1], lambda c: isinstance(c, ft.OutlinedIconButton))
    assert [b.visible for b in share] == [False]  # desktop: no share button

    edit_review(page, "Alice cresceu muito neste semestre.\n\nContinuaremos com histórias.")
    asyncio.run(pdf.on_click(None))

    [(kind, data, filename)] = exporter.calls
    assert kind == "save" and filename.startswith("relatorio-alice-martins-")
    assert "Alice cresceu muito neste semestre." in pdf_text(data)
    assert notice_text(page) == "PDF saved."
    [saved] = repositories.reports.list_for_class(sample_class["id"])
    assert saved["text"].startswith("Alice cresceu muito")  # the edit was saved too


def test_save_text_keeps_the_edits_without_a_pdf(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    review_after_generating(page, repositories, sample_class, exporter)
    save, _ = review_buttons(page)

    edit_review(page, "Texto revisado pela professora.")
    save.on_click(None)

    [saved] = repositories.reports.list_for_class(sample_class["id"])
    assert saved["text"] == "Texto revisado pela professora."
    assert exporter.calls == []  # no PDF
    assert notice_text(page) == "Report saved." and not notice_is_error(page)
    # Nothing left unsaved: going back doesn't ask to discard.
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)
    assert page.dialog is None and "Generate reports" in screen_text(page)


def test_save_text_failure_is_shown(make_page, repositories, sample_class, monkeypatch):
    page = make_page()
    review_after_generating(page, repositories, sample_class)
    save, _ = review_buttons(page)
    edit_review(page, "Outro texto.")

    def broken(report_id, text):
        raise RuntimeError("disk full")

    monkeypatch.setattr(repositories.reports, "update_text", broken)
    save.on_click(None)

    assert notice_is_error(page)
    assert notice_text(page) == "Couldn't save the report. Please try again."


def test_share_pdf_on_phones(make_page, repositories, sample_class):
    exporter = FakeExporter()
    page = make_page()
    page.platform = ft.PagePlatform.ANDROID
    review_after_generating(page, repositories, sample_class, exporter)
    review_buttons(page)  # the same two buttons at the bottom

    [share] = find_all(page.controls[-1], lambda c: isinstance(c, ft.OutlinedIconButton))
    assert share.visible and share.tooltip == "Share PDF"  # at the top
    asyncio.run(share.on_click(None))

    [(kind, data, filename)] = exporter.calls
    assert kind == "share" and data.startswith(b"%PDF") and filename.endswith(".pdf")


def test_review_buttons_in_portuguese(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)
    find_button(page.controls[-1], "Abrir").on_click(None)

    save, pdf = layout(page)[1].content.controls
    assert find_button(save, "Salvar texto") is save and find_button(pdf, "Gerar PDF") is pdf
    save.on_click(None)
    assert notice_text(page) == "Relatório salvo."


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
    area = edit_review(page, "   ")
    save, pdf = review_buttons(page)

    asyncio.run(pdf.on_click(None))
    assert exporter.calls == [] and area.error == "The report is empty."
    area.error = None
    save.on_click(None)
    assert area.error == "The report is empty."
    assert repositories.reports.list_for_class(sample_class["id"])[0]["text"].strip()


def test_saved_reports_can_be_reopened(make_page, repositories, sample_class):
    page = make_page()
    review_after_generating(page, repositories, sample_class)
    find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton))[0].on_click(None)

    [row] = find_all(page.controls[-1], lambda c: isinstance(c, ft.Container)
                     and str(c.data).startswith("report:"))
    row.on_click(None)

    assert "Report | Alice Martins" in screen_text(page)


def saved_rows(page):
    return find_all(page.controls[-1], lambda c: isinstance(c, ft.Container)
                    and str(c.data).startswith("report:"))


def delete_buttons(page):
    return find_all(page.controls[-1], lambda c: isinstance(c, ft.IconButton)
                    and str(c.data).startswith("delete:"))


def generate_for_alice(page, repositories, sample_class, ai=None):
    add_events(repositories, sample_class)
    app = open_reports(page, repositories, sample_class, ai=ai)
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)
    return app


def test_a_saved_report_is_deleted_after_confirming(make_page, repositories, sample_class):
    page = make_page()
    generate_for_alice(page, repositories, sample_class)
    [report] = repositories.reports.list_for_class(sample_class["id"])
    assert "Report ready" in screen_text(page)
    body = layout(page)[0]
    [button] = delete_buttons(page)
    assert button.tooltip == "Delete report" and button.icon == ft.Icons.DELETE_OUTLINE

    button.on_click(None)

    dialog = page.dialog
    texts = " | ".join(collect_texts(dialog))
    assert "Delete report?" in texts and "The report of Alice Martins" in texts
    assert "This can't be undone" in texts and "learning story are not affected" in texts
    find_button(dialog, "Delete").on_click(None)

    assert repositories.reports.list_for_class(sample_class["id"]) == []
    assert repositories.reports.get(report["id"]) is None
    assert saved_rows(page) == [] and "No reports yet." in screen_text(page)
    assert "Report ready" not in screen_text(page)  # no "Open" pointing to a deleted report
    assert notice_text(page) == "Report deleted."  # at the top of the screen
    assert page.dialog is None
    assert layout(page)[0] is body  # the page didn't jump back to the top
    assert len(repositories.events.story(report["student_id"])) == 3  # events are kept


def test_cancel_keeps_the_report(make_page, repositories, sample_class):
    page = make_page()
    generate_for_alice(page, repositories, sample_class)
    delete_buttons(page)[0].on_click(None)

    find_button(page.dialog, "Cancel").on_click(None)

    assert page.dialog is None
    assert len(repositories.reports.list_for_class(sample_class["id"])) == 1
    assert len(saved_rows(page)) == 1


def test_a_failed_delete_shows_an_error(make_page, repositories, sample_class, monkeypatch):
    page = make_page()
    generate_for_alice(page, repositories, sample_class)
    delete_buttons(page)[0].on_click(None)

    def broken(report_id):
        raise RuntimeError("disk full")

    monkeypatch.setattr(repositories.reports, "delete", broken)
    find_button(page.dialog, "Delete").on_click(None)

    assert "Couldn't delete the report. Please try again." in collect_texts(page.dialog)
    assert len(repositories.reports.list_for_class(sample_class["id"])) == 1


def test_reports_cannot_be_deleted_while_generating(make_page, repositories, sample_class):
    page = make_page()
    seen = {}

    class SpyAI(FakeAI):
        async def complete(self, system, user):
            seen["disabled"] = [b.disabled for b in delete_buttons(page)]
            return await super().complete(system, user)

    alice = by_name(repositories, sample_class["id"], "Alice Martins")
    repositories.reports.add(sample_class["id"], alice["id"], TODAY - timedelta(days=30),
                             TODAY, "Antigo", 1, "m")  # a report saved before
    generate_for_alice(page, repositories, sample_class, ai=SpyAI())

    assert seen["disabled"] == [True]  # while the AI was writing
    assert [b.disabled for b in delete_buttons(page)] == [False, False]  # enabled again


def test_delete_report_in_portuguese(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    report_chips(page)["Alice Martins (2)"].on_select(None)
    generate(page)

    [button] = delete_buttons(page)
    assert button.tooltip == "Excluir relatório"
    button.on_click(None)
    texts = " | ".join(collect_texts(page.dialog))
    assert "Excluir relatório?" in texts and "O relatório de Alice Martins" in texts
    find_button(page.dialog, "Excluir").on_click(None)
    assert notice_text(page) == "Relatório excluído."


def test_report_screen_in_portuguese(make_page, repositories, sample_class):
    add_events(repositories, sample_class)
    page = make_page()
    open_reports(page, repositories, sample_class, language="pt")
    text = screen_text(page)
    for expected in ("Período", "De", "Até", "Alunos", "Turma", "Gerar relatórios",
                     "Os nomes são trocados antes do envio"):
        assert expected in text, expected
