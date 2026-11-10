"""What is sent to the AI to write a report, and how names are protected.

Only what the report needs is sent: the event descriptions and dates of the
period, the teacher's extra information, and the child's age. Never photos,
birth dates or the class name. Names are pseudonymized: the child becomes
`[NOME]` and other children become "a classmate"; the real first name is put
back on the device, after the answer arrives.

The AI must not invent anything. Besides strict rules in the prompt:
- each source (the teacher's notes, each record) gets a number, and every
  paragraph of the answer must end with the numbers it is based on, e.g. [1][3];
- `ground_answer` checks them on the device: a paragraph without a valid source
  is removed, then the numbers are taken out of the text;
- the length asked for depends on how many records there are (few records →
  short report), so the AI is never pushed to fill space;
- photo-only records are not mentioned (the AI can't see the photos).

The teacher may add instructions (structure, standards, sections, order,
tone). They change the FORM of the report, never its content: the rules above
still apply. When there are instructions, section titles are allowed (short
lines without a source, kept only if a section with sources follows).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from i18n import Translator

PLACEHOLDER = "[NOME]"

_ACCENTS = {
    "a": "aáàâãä", "e": "eéèêë", "i": "iíìîï", "o": "oóòôõö", "u": "uúùûü",
    "c": "cç", "n": "nñ", "y": "yý",
}

SYSTEM_PROMPTS = {
    "pt": (
        "Você é uma professora experiente de Educação Infantil no Brasil. Você escreve "
        "relatórios descritivos individuais, como os entregues às famílias ao fim de cada "
        "período, com linguagem acolhedora, clara e profissional.\n"
        "\n"
        "REGRA MAIS IMPORTANTE: use SOMENTE o que está escrito nas fontes numeradas que a "
        "professora enviou. Você reorganiza, une e redige melhor o que foi registrado; você "
        "NÃO acrescenta nada.\n"
        "- Não invente fatos, atividades, falas, sentimentos, materiais, lugares, datas, "
        "habilidades ou avanços que não estejam escritos nas fontes.\n"
        "- Não generalize a partir de um único registro (por exemplo, \"sempre\", "
        "\"frequentemente\", \"demonstra domínio\") se as fontes não disserem isso.\n"
        "- Não use a idade para supor o que a criança sabe ou faz, nem compare com o "
        "\"esperado para a idade\".\n"
        "- Se houver poucos registros, escreva um relatório curto. Um texto curto e fiel é "
        "melhor do que um texto longo com informações inventadas.\n"
        "- Não avalie, não dê notas, não compare com outras crianças e não faça "
        "diagnósticos.\n"
        "- Você pode citar o campo de experiência da BNCC a que uma vivência registrada se "
        "relaciona (O eu, o outro e o nós; Corpo, gestos e movimentos; Traços, sons, cores "
        "e formas; Escuta, fala, pensamento e imaginação; Espaços, tempos, quantidades, "
        "relações e transformações), sem atribuir à criança aprendizagens que as fontes não "
        "descrevem.\n"
        "- Último parágrafo: próximos passos, propostas para continuar apoiando a criança, "
        "baseadas apenas nos interesses e vivências que aparecem nas fontes.\n"
        "\n"
        "ORIENTAÇÕES DA PROFESSORA: se a professora enviar orientações (estrutura, seções, "
        "ordem, padrões, tom), siga-as. Elas mudam a FORMA do relatório, nunca o conteúdo, "
        "e não anulam as regras acima: se pedirem algo que as fontes não têm, deixe essa "
        "parte de fora em vez de inventar. Se pedirem seções, escreva o título de cada seção "
        "sozinho em uma linha (sem fonte) e o texto da seção em parágrafos com fontes; omita "
        "as seções sem fontes.\n"
        "\n"
        "FONTES: termine CADA parágrafo com os números das fontes em que ele se baseia, "
        "entre colchetes, por exemplo: [1][3]. Todo parágrafo precisa de pelo menos uma "
        "fonte; um parágrafo sem fonte será apagado.\n"
        "\n"
        "Forma: refira-se à criança somente como [NOME] ou \"a criança\", sem pronomes nem "
        "palavras que indiquem gênero. Terceira pessoa, texto corrido. Responda somente com "
        "o texto do relatório, sem markdown e sem listas; títulos só se as orientações da "
        "professora pedirem seções."
    ),
    "en": (
        "You are an experienced early childhood education teacher. You write individual "
        "descriptive reports, like the ones shared with families at the end of each term, "
        "in a warm, clear and professional tone.\n"
        "\n"
        "MOST IMPORTANT RULE: use ONLY what is written in the numbered sources the teacher "
        "sent. You organize, combine and word better what was recorded; you do NOT add "
        "anything.\n"
        "- Do not invent facts, activities, quotes, feelings, materials, places, dates, "
        "skills or progress that are not written in the sources.\n"
        "- Do not generalize from a single record (e.g. \"always\", \"often\", "
        "\"has mastered\") unless the sources say so.\n"
        "- Do not use the age to assume what the child knows or does, and do not compare "
        "with what is \"expected for the age\".\n"
        "- If there are few records, write a short report. A short, faithful text is better "
        "than a long one with invented information.\n"
        "- Do not grade, do not compare with other children and do not diagnose.\n"
        "- You may name the developmental area a recorded experience relates to "
        "(social-emotional, communication and language, physical, creative expression, "
        "thinking and exploration), without crediting the child with learning the sources "
        "do not describe.\n"
        "- Last paragraph: next steps, ideas to keep supporting the child, based only on the "
        "interests and experiences that appear in the sources.\n"
        "\n"
        "TEACHER'S INSTRUCTIONS: if the teacher sends instructions (structure, sections, "
        "order, standards, tone), follow them. They change the FORM of the report, never its "
        "content, and they do not cancel the rules above: if they ask for something the "
        "sources don't have, leave that part out instead of inventing it. If they ask for "
        "sections, write each section title alone on its own line (no source) and the "
        "section text in paragraphs with sources; leave out sections with no sources.\n"
        "\n"
        "SOURCES: end EVERY paragraph with the numbers of the sources it is based on, in "
        "square brackets, e.g. [1][3]. Every paragraph needs at least one source; a paragraph "
        "without a source will be deleted.\n"
        "\n"
        "Form: refer to the child only as [NOME] or \"the child\", with no gendered pronouns "
        "or words. Third person, flowing text. Answer only with the report text, with no "
        "markdown and no lists; titles only if the teacher's instructions ask for sections."
    ),
}

USER_LABELS = {
    "pt": {
        "period": "Período: {start} a {end}",
        "age": "Idade da criança no fim do período: {age}",
        "sources": "Fontes ({count}):",
        "notes": "[{number}] Informações da professora sobre a criança: {text}",
        "event": "[{number}] Registro de {date}: {text}",
        "with": "com {count} colega(s)",
        "length": (
            "Escreva no máximo {paragraphs} parágrafo(s), incluindo os próximos passos, "
            "e termine cada parágrafo com as suas fontes, por exemplo [1]."
        ),
        "instructions": (
            "Orientações da professora para o relatório (forma, estrutura e padrões; elas "
            "não autorizam inventar nada, e os títulos de seção não contam como parágrafos):"
        ),
        "classmate": "um(a) colega",
    },
    "en": {
        "period": "Period: {start} to {end}",
        "age": "Child's age at the end of the period: {age}",
        "sources": "Sources ({count}):",
        "notes": "[{number}] The teacher's notes about the child: {text}",
        "event": "[{number}] Record of {date}: {text}",
        "with": "with {count} classmate(s)",
        "length": (
            "Write at most {paragraphs} paragraph(s), including the next steps, and end "
            "each paragraph with its sources, e.g. [1]."
        ),
        "instructions": (
            "The teacher's instructions for the report (form, structure and standards; they "
            "never allow inventing anything, and section titles don't count as paragraphs):"
        ),
        "classmate": "a classmate",
    },
}


def max_paragraphs(source_count: int) -> int:
    """Few sources → short report: the AI is never asked to fill space."""
    if source_count <= 1:
        return 2
    if source_count <= 3:
        return 3
    if source_count <= 6:
        return 4
    return 6


def _name_pattern(name: str) -> str:
    """Regex for a name: accent-insensitive; first letter must be uppercase.

    Requiring the capital letter avoids replacing words that are also names
    (e.g. "clara" = light, "luna"...) in the middle of a sentence.
    """
    parts = []
    for index, char in enumerate(name):
        base = unicodedata.normalize("NFKD", char.lower())[0]
        variants = _ACCENTS.get(base, re.escape(char.lower()))
        if index == 0:
            parts.append("[" + variants.upper() + "]")
        else:
            if base in _ACCENTS:
                parts.append("(?i:[" + variants + "])")
            else:
                parts.append(f"(?i:{re.escape(char)})")
    return "".join(parts)


def _replace_names(text: str, names: list[str], replacement: str) -> str:
    names = sorted({n for n in names if len(n) >= 2}, key=len, reverse=True)
    if not names:
        return text
    pattern = re.compile(r"(?<!\w)(" + "|".join(_name_pattern(n) for n in names) + r")(?!\w)")
    return pattern.sub(replacement, text)


@dataclass
class Pseudonymizer:
    child_name: str
    other_names: list[str]
    classmate: str

    def hide(self, text: str) -> str:
        child = [self.child_name, *self.child_name.split()[:1]]
        others = [n for name in self.other_names for n in (name, name.split()[0])]
        others = [n for n in others if n not in child]  # same first name: treat as the child
        text = _replace_names(text, child, PLACEHOLDER)
        return _replace_names(text, others, self.classmate)

    def restore(self, text: str) -> str:
        first_name = self.child_name.split()[0]
        return re.sub(r"\[\s*nome\s*\]", first_name, text, flags=re.IGNORECASE)


def build_prompt(
    tr: Translator,
    student: dict[str, Any],
    events: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    classmates: list[str],
    instructions: str = "",
) -> tuple[str, str, Pseudonymizer]:
    """(system prompt, user prompt, pseudonymizer to restore the answer).

    The sources are numbered 1..n (the teacher's notes first, then the records
    with a description, oldest first); `ground_answer` checks the numbers.
    `instructions`: the teacher's format instructions (names hidden too).
    """
    labels = USER_LABELS[tr.language]
    names = Pseudonymizer(student["name"], classmates, labels["classmate"])
    sources = []
    if student.get("notes"):
        sources.append(("notes", {"text": names.hide(student["notes"])}))
    # Photo-only records are left out: the AI can't see photos and would guess.
    described = sorted((e for e in events if e["description"]), key=lambda e: e["occurred_on"])
    for event in described:
        text = names.hide(event["description"])
        others = len(event["student_ids"]) - 1
        if others:
            text += f" ({labels['with'].format(count=others)})"
        sources.append(("event", {"date": tr.format_date(event["occurred_on"]), "text": text}))

    lines = [labels["period"].format(start=tr.format_date(period_start),
                                     end=tr.format_date(period_end))]
    if student.get("birth_date"):
        lines.append(labels["age"].format(age=tr.format_age(student["birth_date"], period_end)))
    lines += ["", labels["sources"].format(count=len(sources))]
    lines += [labels[kind].format(number=number, **fields)
              for number, (kind, fields) in enumerate(sources, start=1)]
    lines += ["", labels["length"].format(paragraphs=max_paragraphs(len(sources)))]
    if instructions.strip():
        lines += ["", labels["instructions"], names.hide(instructions.strip())]
    return SYSTEM_PROMPTS[tr.language], "\n".join(lines), names


def source_count(student: dict[str, Any], events: list[dict[str, Any]]) -> int:
    """How many numbered sources `build_prompt` sends (for `ground_answer`)."""
    return bool(student.get("notes")) + sum(1 for e in events if e["description"])


def clean_answer(text: str) -> str:
    """Plain paragraphs: remove markdown marks and extra blank lines."""
    # Reasoning models may put their "thinking" before the answer.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Markdown titles ("## Linguagem", a line all in bold) become their own
    # paragraph, not glued to the text under them.
    # [ \t]* (not \s*): "\s" would also eat the blank lines between paragraphs.
    text = re.sub(r"^[ \t]*#+[ \t]*(.*)$", r"\n\1\n", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*(\*\*|__)([^*_\n]+)\1[ \t]*:?[ \t]*$", r"\n\2\n", text,
                  flags=re.MULTILINE)
    text = re.sub(r"\*\*|__", "", text)  # bold
    # A list item (the AI was asked not to use lists) becomes its own paragraph.
    text = re.sub(r"^[ \t]*[-*•][ \t]+", "\n", text, flags=re.MULTILINE)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        paragraphs += _split_title(block)
    paragraphs = [" ".join(p.split()) for p in paragraphs]
    return "\n\n".join(p for p in paragraphs if p)


def _split_title(block: str) -> list[str]:
    """"Matemática\n[NOME] contou..." -> the title and the text as two paragraphs.

    Only when the first line looks like a title and the next line starts a new
    sentence (uppercase or "["), so a sentence broken over two lines is kept.
    """
    lines = [line for line in block.strip().split("\n") if line.strip()]
    if len(lines) < 2:
        return [block]
    first, rest = lines[0].strip(), lines[1].strip()
    starts_sentence = rest[0].isupper() or rest[0] == "["
    if is_title(first) and (first.endswith(":") or starts_sentence) and "[" not in first:
        return [first, "\n".join(lines[1:])]
    return [block]


# "[1]", "[1][3]", "[1, 3]", "[1 e 3]", "[1 and 3]"
_CITATION = re.compile(r"\[\s*\d+(?:\s*(?:,|;|e|and)\s*\d+)*\s*\]", re.IGNORECASE)


@dataclass
class Grounding:
    text: str
    kept: int = 0  # paragraphs with at least one valid source (titles not counted)
    removed: list[str] = field(default_factory=list)  # paragraphs without a valid source
    unknown_sources: set[int] = field(default_factory=set)  # numbers that don't exist
    checked: bool = True  # False: the AI cited nothing at all, nothing could be checked


def is_title(paragraph: str) -> bool:
    """A section title: a short line that is not a sentence (e.g. "Linguagem:")."""
    text = paragraph.strip()
    return 0 < len(text) <= 80 and len(text.split()) <= 10 and text[-1] not in ".!?;,"


def ground_answer(text: str, sources: int, allow_titles: bool = False) -> Grounding:
    """Keep only paragraphs based on the sources, and take the numbers out of the text.

    With `allow_titles` (the teacher asked for a structure), a title without a
    source is kept when a paragraph with sources follows it (an empty section
    is dropped).

    If the AI cited no source at all (it ignored the format), nothing can be
    checked: the text is kept and `checked` is False (the caller logs it; the
    teacher reviews every draft anyway).
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not any(_CITATION.search(p) for p in paragraphs):
        return Grounding(text=text, kept=len(paragraphs), checked=False)
    result = Grounding(text="")
    kept: list[str] = []
    pending_title: str | None = None  # waits for a paragraph with sources
    for paragraph in paragraphs:
        numbers = {int(n) for c in _CITATION.findall(paragraph) for n in re.findall(r"\d+", c)}
        valid = {n for n in numbers if 1 <= n <= sources}
        result.unknown_sources |= numbers - valid
        clean = " ".join(_CITATION.sub(" ", paragraph).split())
        clean = re.sub(r"\s+([.,;:!?])", r"\1", clean)  # "torre [1]." -> "torre."
        if not clean:
            continue
        if valid:
            if pending_title is not None:
                kept.append(pending_title)
                pending_title = None
            kept.append(clean)
            result.kept += 1
        elif allow_titles and not numbers and is_title(clean):
            pending_title = clean  # a following title replaces it: that section was empty
        else:
            result.removed.append(clean)
    result.text = "\n\n".join(kept)
    return result
