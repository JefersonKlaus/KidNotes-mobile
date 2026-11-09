"""What is sent to the AI to write a report, and how names are protected.

Only what the report needs is sent: the event descriptions and dates of the
period, the teacher's extra information, and the child's age. Never photos,
birth dates or the class name. Names are pseudonymized: the child becomes
`[NOME]` and other children become "a classmate"; the real first name is put
back on the device, after the answer arrives.
"""

import re
import unicodedata
from dataclasses import dataclass
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
        "relatórios descritivos individuais de desenvolvimento e aprendizagem, como os "
        "entregues às famílias ao fim de cada período, com linguagem acolhedora, clara "
        "e profissional.\n"
        "Regras:\n"
        "- Baseie-se somente nos registros e informações fornecidos. Não invente fatos, "
        "falas, habilidades ou situações.\n"
        "- Descreva conquistas, interesses, interações, descobertas e avanços. Não avalie, "
        "não dê notas, não compare com outras crianças e não faça diagnósticos.\n"
        "- Quando fizer sentido, relacione as vivências aos campos de experiência da BNCC "
        "(O eu, o outro e o nós; Corpo, gestos e movimentos; Traços, sons, cores e formas; "
        "Escuta, fala, pensamento e imaginação; Espaços, tempos, quantidades, relações e "
        "transformações), em texto corrido, sem listas.\n"
        "- Refira-se à criança somente como [NOME] ou \"a criança\". Não use pronomes nem "
        "palavras que indiquem gênero.\n"
        "- Escreva em terceira pessoa, de 3 a 6 parágrafos. Termine com um parágrafo de "
        "próximos passos: propostas para continuar apoiando o desenvolvimento.\n"
        "- Responda somente com o texto do relatório, sem título, sem markdown e sem listas."
    ),
    "en": (
        "You are an experienced early childhood education teacher. You write individual "
        "descriptive reports on a child's development and learning, like the ones shared "
        "with families at the end of each term, in a warm, clear and professional tone.\n"
        "Rules:\n"
        "- Use only the records and information provided. Do not invent facts, quotes, "
        "skills or situations.\n"
        "- Describe achievements, interests, interactions, discoveries and progress. Do not "
        "grade, do not compare with other children and do not diagnose.\n"
        "- When it makes sense, relate the experiences to developmental areas "
        "(social-emotional, communication and language, physical, creative expression, "
        "thinking and exploration), in flowing text, without lists.\n"
        "- Refer to the child only as [NOME] or \"the child\". Do not use gendered pronouns "
        "or words.\n"
        "- Write in the third person, 3 to 6 paragraphs. End with a paragraph of next "
        "steps: ideas to keep supporting the child's development.\n"
        "- Answer only with the report text, with no title, no markdown and no lists."
    ),
}

USER_LABELS = {
    "pt": {
        "period": "Período: {start} a {end}",
        "age": "Idade da criança no fim do período: {age}",
        "notes": "Informações da professora sobre a criança:",
        "events": "Registros de momentos significativos ({count}):",
        "with": "com {count} colega(s)",
        "photo_only": "Também há {count} registro(s) somente com foto, sem descrição.",
        "classmate": "um(a) colega",
    },
    "en": {
        "period": "Period: {start} to {end}",
        "age": "Child's age at the end of the period: {age}",
        "notes": "The teacher's notes about the child:",
        "events": "Records of significant moments ({count}):",
        "with": "with {count} classmate(s)",
        "photo_only": "There are also {count} record(s) with only a photo and no description.",
        "classmate": "a classmate",
    },
}


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
) -> tuple[str, str, Pseudonymizer]:
    """(system prompt, user prompt, pseudonymizer to restore the answer)."""
    labels = USER_LABELS[tr.language]
    names = Pseudonymizer(student["name"], classmates, labels["classmate"])
    lines = [labels["period"].format(start=tr.format_date(period_start),
                                     end=tr.format_date(period_end))]
    if student.get("birth_date"):
        lines.append(labels["age"].format(age=tr.format_age(student["birth_date"], period_end)))
    if student.get("notes"):
        lines += ["", labels["notes"], names.hide(student["notes"])]
    described = [e for e in events if e["description"]]
    lines += ["", labels["events"].format(count=len(described))]
    for event in sorted(described, key=lambda e: e["occurred_on"]):
        line = f"- {tr.format_date(event['occurred_on'])}: {names.hide(event['description'])}"
        others = len(event["student_ids"]) - 1
        if others:
            line += f" ({labels['with'].format(count=others)})"
        lines.append(line)
    photo_only = len(events) - len(described)
    if photo_only:
        lines += ["", labels["photo_only"].format(count=photo_only)]
    return SYSTEM_PROMPTS[tr.language], "\n".join(lines), names


def clean_answer(text: str) -> str:
    """Plain paragraphs: remove markdown marks and extra blank lines."""
    # [ \t]* (not \s*): "\s" would also eat the blank lines between paragraphs.
    text = re.sub(r"^[ \t]*#+[ \t]*", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"\*\*|__", "", text)  # bold
    # A list item (the AI was asked not to use lists) becomes its own paragraph.
    text = re.sub(r"^[ \t]*[-*•][ \t]+", "\n", text, flags=re.MULTILINE)
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paragraphs if p)
