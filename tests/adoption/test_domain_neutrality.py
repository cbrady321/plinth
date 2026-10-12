"""Plinth must stay a pure, domain-agnostic pipeline library.

Fails if the package imports any third-party module that is not a declared dependency. Application code
belongs in the consuming project; dataset conventions are declared through ``DatasetSchema``
(``MediaSpec`` / ``ManifestIdentity``), never assumed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "plinth"

# import name -> must be declared in pyproject.toml [project.dependencies]
CORE_IMPORTS = {"pandas", "yaml", "tqdm", "jsonschema"}
# only inside plinth.researcher_ui (the optional `ui` extra)
UI_IMPORTS = {"fastapi", "uvicorn", "pydantic", "httpx", "starlette"}


def _top_level_imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_package_imports_only_declared_dependencies() -> None:
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        in_ui = "researcher_ui" in path.relative_to(SRC).parts
        allowed = CORE_IMPORTS | (UI_IMPORTS if in_ui else set())
        for name in _top_level_imports(path):
            if name == "plinth" or name in sys.stdlib_module_names or name == "__future__":
                continue
            if name not in allowed:
                bad.append(f"{path.relative_to(ROOT)}: imports '{name}'")
    assert not bad, "undeclared / out-of-scope third-party imports:\n" + "\n".join(bad)


def test_declared_core_dependencies_cover_allowed_imports() -> None:
    text = (ROOT / "pyproject.toml").read_text()
    deps_block = text.split("dependencies = [", 1)[1].split("]", 1)[0].lower()
    dist_for = {"yaml": "pyyaml"}
    for name in CORE_IMPORTS:
        assert dist_for.get(name, name) in deps_block, f"{name} is allowed but not a declared dependency"
