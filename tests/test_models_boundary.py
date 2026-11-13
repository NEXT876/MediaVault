"""mediavault/models holds plain data only: it must not import the rest of the package."""

import ast
from pathlib import Path

import mediavault

MODELS = Path(mediavault.__file__).parent / "models"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]


def test_models_import_nothing_from_the_logic():
    offenders = [
        f"{path.name}: {name}"
        for path in sorted(MODELS.glob("*.py"))
        for name in _imports(path)
        if name
        and name.startswith("mediavault")
        and not name.startswith("mediavault.models")
    ]
    assert offenders == []
