"""Dados mockados do prototipo."""

from typing import Any


APP_DATA: dict[str, Any] = {
    "teacher": {
        "name": "Prof. Ana Clara",
        "role": "Educação Infantil",
        "initials": "AC",
    },
    "classes": [
        {
            "id": "maternal-1-manha",
            "name": "Maternal I - Manhã",
            "color": "#F8C8D8",
            "students": [
                {"name": "Alice Martins", "initials": "AM", "color": "#F4A7C1"},
                {"name": "Bento Oliveira", "initials": "BO", "color": "#A8D8EA"},
                {"name": "Clara Souza", "initials": "CS", "color": "#B8E0C8"},
                {"name": "Davi Santos", "initials": "DS", "color": "#F6D6A8"},
                {"name": "Luna Costa", "initials": "LC", "color": "#C9B8E8"},
            ],
        },
        {
            "id": "infantil-2-tarde",
            "name": "Infantil II - Tarde",
            "color": "#B8DCEB",
            "students": [
                {"name": "Gael Lima", "initials": "GL", "color": "#F6D6A8"},
                {"name": "Helena Alves", "initials": "HA", "color": "#F8C8D8"},
                {"name": "João Pedro", "initials": "JP", "color": "#A8D8EA"},
                {"name": "Maya Rocha", "initials": "MR", "color": "#B8E0C8"},
            ],
        },
    ],
}

CHECKLIST: dict[str, list[str]] = {
    "Socioemocional": [
        "Demonstra carinho e respeito pelos colegas",
        "Participa de atividades em grupo",
        "Expressa sentimentos e necessidades",
    ],
    "Linguagem": [
        "Comunica-se com clareza para sua idade",
        "Demonstra interesse por histórias e livros",
        "Amplia seu vocabulário no dia a dia",
    ],
    "Motricidade": [
        "Explora movimentos amplos com segurança",
        "Coordena movimentos finos em atividades",
        "Demonstra interesse por desenhar e criar",
    ],
    "Autonomia": [
        "Realiza pequenas tarefas de cuidado pessoal",
        "Organiza seus materiais com apoio",
        "Faz escolhas durante a rotina",
    ],
}
