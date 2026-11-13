"""Extras stay optional: only the main window may import them."""

from pathlib import Path

import mediavault

PACKAGE = Path(mediavault.__file__).parent
ALLOWED = {PACKAGE / "gui" / "main_window.py"}


def test_only_main_window_imports_extras():
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "extras" not in path.relative_to(PACKAGE).parts
        and path not in ALLOWED
        and any(
            line.lstrip().startswith(
                ("from mediavault.extras", "import mediavault.extras")
            )
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []
