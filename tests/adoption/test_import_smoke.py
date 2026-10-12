"""Import smoke test without domain stages."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "docs" / "schemas" / "pipeline_config.schema.json"

_SMOKE_SCRIPT = """
import json
import sys
from pathlib import Path

root = Path({root!r})
sys.path.insert(0, str(root))

from plinth.dag_structures import DAGConfig, SequentialBlockConfig, StageConfig
from plinth.registry import StageRegistry
from plinth.rows import CoreManifestRow
from plinth.testing import InMemoryStageContext, TypicalStageExecutor

assert StageRegistry.list_stages() == [], "StageRegistry must start empty before any registration"
assert CoreManifestRow is not None
assert InMemoryStageContext is not None
assert TypicalStageExecutor is not None

empty_dag = DAGConfig(root=SequentialBlockConfig(name="root", children=[]))
assert empty_dag.to_dict() == {{"type": "sequential", "name": "root", "children": []}}

schema_valid_dag = DAGConfig(
    root=SequentialBlockConfig(
        name="root",
        children=[StageConfig(name="placeholder_stage")],
    )
)
doc = {{
    "name": "smoke",
    "version": "0.0.0",
    "dag": schema_valid_dag.to_dict(),
    "params": {{}},
}}

schema_path = root / "docs" / "schemas" / "pipeline_config.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))

import jsonschema
jsonschema.Draft202012Validator(schema).validate(doc)
print("import smoke ok")
"""


def test_import_smoke_in_clean_subprocess() -> None:
    assert SCHEMA_PATH.exists()
    script = _SMOKE_SCRIPT.format(root=str(PROJECT_ROOT))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
