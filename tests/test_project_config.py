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
