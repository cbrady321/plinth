"""Persisted dataset schemas state their format (E55)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.structures import SCHEMA_FORMAT, DatasetSchema


def test_written_schema_is_explicit_and_round_trips(tmp_path: Path) -> None:
    schema = DatasetSchema(
        unique_key=["entity_id", "batch"],
        identity=ManifestIdentity(hierarchy_keys=["batch"], key_types={"batch": "int"}, key_defaults={"batch": 1}),
        columns={"entity_id": "str", "batch": "int"},
    )
    path = tmp_path / "dataset_schema.yaml"
    schema.to_yaml(path)

    data = yaml.safe_load(path.read_text())
    assert data["schema_format"] == SCHEMA_FORMAT
    assert set(data) == {"schema_format", "unique_key", "identity", "columns", "media"}
    assert DatasetSchema.from_yaml(path) == schema


@pytest.mark.parametrize(
    ("schema_format", "message"),
    [(None, "no supported schema_format"), (0, "no supported schema_format"), (SCHEMA_FORMAT + 1, "upgrade plinth")],
)
def test_unsupported_schema_format_is_rejected(tmp_path: Path, schema_format: object, message: str) -> None:
    data = DatasetSchema().to_dict()
    if schema_format is None:
        data.pop("schema_format")
    else:
        data["schema_format"] = schema_format
    path = tmp_path / "dataset_schema.yaml"
    path.write_text(yaml.dump(data))

    with pytest.raises(ValueError, match=message):
        DatasetSchema.from_yaml(path)
    with pytest.raises(ValueError, match=message):
        DatasetSchema.declared_in(tmp_path)


def test_non_integer_schema_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid schema_format"):
        DatasetSchema.from_dict({"schema_format": "two"})


def test_directory_without_schema_declares_none(tmp_path: Path) -> None:
    (tmp_path / "manifest.csv").write_text("entity_id,file_path\na,files/a.bin\n")
    assert DatasetSchema.declared_in(tmp_path) is None
    assert DatasetSchema.for_directory(tmp_path) == DatasetSchema()
