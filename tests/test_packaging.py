"""What the built app actually contains.

Every test in this suite runs against the source tree, where every package is
importable because the working directory is the repository. The bundle is a
different filesystem, and it only contains what build.sh copied into it - so a
new package can pass the entire suite and still produce an app that dies on
launch with ModuleNotFoundError. That happened with the studios package.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

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
