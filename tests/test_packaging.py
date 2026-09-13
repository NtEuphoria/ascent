"""What the built app actually contains.

Every test in this suite runs against the source tree, where every package is
importable because the working directory is the repository. The bundle is a
different filesystem, and it only contains what build.sh copied into it - so a
new package can pass the entire suite and still produce an app that dies on
launch with ModuleNotFoundError. That happened with the studios package.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _local_packages():
    """Top-level directories in the repo that are Python packages."""
    skip = {".venv", "dist", "build", "tests", "plugins", "docs", "macos"}
    return {path.parent.name
            for path in ROOT.glob("*/__init__.py")
            if path.parent.name not in skip}


def _imported_by_app():
    """Top-level modules app.py imports, restricted to ones in this repo."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return {name for name in names if (ROOT / name).is_dir()}


def test_the_build_finds_packages_rather_than_listing_them():
    """A hardcoded list is a list somebody has to remember to update, and the
    failure only appears after installing."""
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    assert "cp -R calculators utils" not in build, \
        "build.sh hardcodes the package list again"
    assert "__init__.py" in build and "PACKAGES" in build


def test_every_package_app_imports_would_be_bundled():
    """The bundle copies packages by finding __init__.py. A local package
    without one is invisible to that search and would not ship."""
    for name in _imported_by_app():
        assert (ROOT / name / "__init__.py").exists(), \
            f"app.py imports {name}, which has no __init__.py and so would " \
            f"not be copied into the bundle"


def test_app_imports_nothing_local_that_is_not_a_package():
    missing = _imported_by_app() - _local_packages()
    assert not missing, f"app.py imports non-package directories: {missing}"


def test_the_installed_bundle_has_every_package():
    """Checked against the real installed app when one is present.

    Skipped rather than failed when ASCENT is not installed, because a clean
    checkout on another machine has no bundle to inspect and that is not a
    defect in the code.
    """
    bundle = pathlib.Path("/Applications/ASCENT.app/Contents/Resources/app")
    if not bundle.is_dir():
        import pytest
        pytest.skip("ASCENT is not installed on this machine")
    for name in _imported_by_app():
        assert (bundle / name).is_dir(), \
            f"the installed app is missing the {name} package - rebuild with " \
            f"./install.sh"


def test_runtime_data_directories_are_bundled_too():
    """assets/ is not a Python package, so the package search cannot find it.
    The Studios card reads its hero from there and would fall back to the
    drawn placeholder in the installed app while looking right in the dev
    server - the same failure the studios package had, one directory over."""
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    assert "for DATA in assets" in build, "build.sh no longer copies assets/"


def test_the_installed_bundle_has_the_studios_hero():
    bundle = pathlib.Path("/Applications/ASCENT.app/Contents/Resources/app")
    if not bundle.is_dir():
        import pytest
        pytest.skip("ASCENT is not installed on this machine")
    if not (ROOT / "assets" / "studios-hero.png").is_file():
        import pytest
        pytest.skip("no hero image in the source tree to bundle")
    assert (bundle / "assets" / "studios-hero.png").is_file(), \
        "the installed app is missing the Studios hero - rebuild with ./install.sh"


def test_the_bootstrap_notices_a_changed_requirements_file():
    """It used to return as soon as it saw the streamlit binary, so an update
    that ADDED a dependency never installed it - the environment looked fine
    and the new feature was quietly missing. That is exactly what happened
    when pyserial arrived: every existing installation kept a venv with no
    serial support in it, and the Live section said serial was unavailable."""
    swift = (ROOT / "macos" / "main.swift").read_text(encoding="utf-8")
    assert "requirementsStampPath" in swift
    assert "updateRuntimeIfNeeded" in swift
    # The stamp has to be written on the first-run path too, or every second
    # launch would think the requirements had changed.
    assert swift.count("requirementsStampPath") >= 3


def test_every_requirement_is_pinned_or_bounded():
    """The app builds its environment on first launch, so an unbounded range
    lets a future release install something this interface has never seen."""
    import re

    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert re.search(r"[=<>]", line), f"{line!r} has no version bound"
