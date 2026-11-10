"""In-memory mock data for the prototype.

Classes, students and events are stored in the encrypted database (see
`database/`); only the teacher profile is still static.
"""

from typing import Any

APP_DATA: dict[str, Any] = {
    "teacher": {
        "name": "Prof. Ana Clara",
        "role": "Educação Infantil",
        "initials": "AC",
    },
}
