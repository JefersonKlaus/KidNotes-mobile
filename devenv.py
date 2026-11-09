"""Development only: load a `.env` file (next to main.py) into the environment.

Lets each developer keep local settings, like GROQ_API_KEY, in one file
instead of setting them in every terminal. Copy `.env.example` to `.env`.

- Only `KEY=value` lines; `#` comments, blank lines and `export KEY=value`
  are accepted; values may be quoted.
- Variables already set in the shell win (they are not overwritten).
- Ignored inside a packaged app (`flet build`): `.env` is git-ignored and
  left out of the package, and the app never reads it on a phone.
"""

import os
from pathlib import Path

from flet.utils import is_embedded

DEFAULT_PATH = Path(__file__).resolve().parent / ".env"


def load_dev_env(path: Path = DEFAULT_PATH) -> dict[str, str]:
    """Returns the variables that were set from the file."""
    if is_embedded() or not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
