# KidNotes-mobile
# RelatórioFácil Infantil

CORE inicial mockado de um aplicativo mobile em Python puro com Flet. O fluxo
visual implementado é:

**Turmas → Alunos → Checklist de avaliação → Relatório pedagógico mockado**

## Executar

Instale o Flet e execute:

```powershell
pip install flet
flet run main.py
```

Os dados ficam em memória no [`data.py`](./data.py), sem banco de dados ou
integração de IA nesta etapa.

## Estrutura

- [`main.py`](./main.py): ponto de entrada do Flet.
- [`app.py`](./app.py): estado da sessão e roteamento entre telas.
- [`data.py`](./data.py): dados mockados e itens do checklist.
- [`theme.py`](./theme.py): tokens do design system.
- [`components.py`](./components.py): componentes visuais compartilhados.
- [`screens/dashboard.py`](./screens/dashboard.py): dashboard e lista de turmas.
- [`screens/students.py`](./screens/students.py): lista de alunos.
- [`screens/assessment.py`](./screens/assessment.py): checklist e relatório mockado.