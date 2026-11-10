"""Guards for pyproject.toml settings that are easy to break by accident."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

tomllib = pytest.importorskip("tomllib")  # Python 3.11+

PYPROJECT = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8"))


def names(requirements):
    return {Requirement(r).name for r in requirements}


def test_dev_group_installs_every_app_dependency():
    # `pip install --group dev` does not install [project].dependencies.
    app = names(PYPROJECT["project"]["dependencies"])
    dev = names(PYPROJECT["dependency-groups"]["dev"])
    assert app <= dev, f"missing in the dev group: {app - dev}"


def test_tests_are_not_bundled_into_the_mobile_app():
    assert "tests" in PYPROJECT["tool"]["flet"]["app"]["exclude"]


def test_ruff_is_pinned_in_the_dev_group():
    # CI installs exactly this version (.github/workflows/ci.yml reads it from here),
    # so `ruff check .` gives the same result on every machine.
    [ruff] = [Requirement(r) for r in PYPROJECT["dependency-groups"]["dev"]
              if Requirement(r).name == "ruff"]
    assert str(ruff.specifier).startswith("=="), "pin ruff to an exact version"


def test_ci_runs_lint_and_tests():
    workflow = (Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml").read_text(
        "utf-8"
    )
    assert "ruff check" in workflow and "pytest" in workflow

