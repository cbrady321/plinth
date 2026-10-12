

import numpy as np
import pandas as pd
import pytest

from plinth.dataset.identity import ManifestIdentity, apply_column_aliases, normalize_entity_id
from plinth.dataset.structures import DatasetManifest, DatasetSchema

# Rows are slots within a labelled batch of an entity; a slot number may be missing. Declared
# explicitly, since the default identity is flat.
HIERARCHICAL = DatasetSchema(
    identity=ManifestIdentity(
        hierarchy_keys=["batch", "slot"],
        disambiguator="filename",
        key_types={"slot": "optional_int"},
    )
)


class TestDatasetManifest:
    @pytest.fixture
    def sample_manifest(self):
        df = pd.DataFrame({
            "entity_id": ["p1", "p1"],
            "batch": [1, 1],
            "slot": [None, 1],
            "filename": ["f1.bin", "f1_1.bin"],
            "file_path": ["/tmp/f1.bin", "/tmp/f1_1.bin"],
            "custom_col": ["a", "b"],
        })
        return DatasetManifest(df, schema=HIERARCHICAL)

    def test_initialization(self):
        m = DatasetManifest()
        assert m.df.empty
        assert "entity_id" in m.df.columns

        df = pd.DataFrame({"entity_id": ["p1"], "batch": [1], "slot": [None]})
        m = DatasetManifest(df)
        assert len(m) == 1

    def test_row_access(self, sample_manifest):
        assert sample_manifest[0]["filename"] == "f1.bin"
        assert list(sample_manifest.df["entity_id"]) == ["p1", "p1"]

    def test_column_alias_ingest(self):
        df = pd.DataFrame({
            "record_id": ["s1"],
            "batch": [1],
            "slot": [None],
            "filename": ["a.bin"],
        })
        schema = DatasetSchema(identity=ManifestIdentity(column_aliases={"record_id": "entity_id"}))
        manifest = DatasetManifest(df, schema=schema)
        assert "entity_id" in manifest.df.columns
        assert manifest.df.iloc[0]["entity_id"] == "s1"

    def test_add_row(self):
        m = DatasetManifest()
        m.add_row({"entity_id": "p2", "batch": 1, "slot": None})
        assert len(m) == 1
        assert m.df.iloc[0]["entity_id"] == "p2"

    def test_update_entry_by_keys(self, sample_manifest):
        sample_manifest.update_entry_by_keys(
            {"entity_id": "p1", "batch": 1, "slot": 1, "filename": "f1_1.bin"},
            {"custom_col": "updated"},
        )
        assert sample_manifest.df.iloc[1]["custom_col"] == "updated"
        assert sample_manifest.df.iloc[0]["custom_col"] == "a"

    def test_merge_no_conflict(self, sample_manifest):
        other_df = pd.DataFrame({
            "entity_id": ["p2"],
            "batch": [1],
            "slot": [None],
            "filename": ["f2.bin"],
            "custom_col": ["c"],
        })
        other = DatasetManifest(other_df, schema=HIERARCHICAL)

        merged = sample_manifest.merge(other)
        assert len(merged) == 3
        assert "p2" in merged.df["entity_id"].tolist()

    def test_merge_deduplication(self, sample_manifest):
        other = DatasetManifest(sample_manifest.df.copy(), schema=HIERARCHICAL)
        merged = sample_manifest.merge(other)
        assert len(merged) == 2

    def test_merge_conflict_prefers_update(self, sample_manifest):
        other_df = sample_manifest.df.copy()
        other_df.loc[0, "custom_col"] = "CONFLICT"
        other = DatasetManifest(other_df, schema=HIERARCHICAL)
        merged = sample_manifest.merge(other)
        mask = (merged.df["entity_id"].astype(str) == "p1") & (
            merged.df["slot"].isna() | (merged.df["slot"] == "")
        )
        assert merged.df.loc[mask, "custom_col"].iloc[0] == "CONFLICT"


class TestDatasetSchema:
    def test_validation(self):
        schema = DatasetSchema(columns={"required": "str"})

        df = pd.DataFrame({
            "entity_id": ["p1"],
            "batch": [1],
            "slot": [None],
            "filename": ["f1.bin"],
            "required": ["v"],
        })
        schema.validate_dataframe(df)

        bad_df = pd.DataFrame({
            "entity_id": ["p1"],
            "batch": [1],
            "slot": [None],
            "filename": ["f1.bin"],
        })
        with pytest.raises(ValueError, match="missing required columns"):
            schema.validate_dataframe(bad_df)

        dupe_df = pd.DataFrame({
            "entity_id": ["p1", "p1"],
            "batch": [1, 1],
            "slot": [None, None],
            "filename": ["f1.bin", "f1.bin"],
            "required": ["v", "v"],
        })
        with pytest.raises(ValueError, match="Duplicate entries"):
            schema.validate_dataframe(dupe_df)

    def test_default_identity_is_flat(self):
        keys = DatasetSchema().effective_unique_key({"entity_id", "batch", "slot", "filename"})
        assert keys == ["entity_id"]

    def test_effective_unique_key_from_declared_identity(self):
        keys = HIERARCHICAL.effective_unique_key({"entity_id", "batch", "slot", "filename"})
        assert keys == ["entity_id", "batch", "slot", "filename"]


class TestEntityIdNormalization:
    def test_normalize_entity_id_handles_nan(self):
        assert normalize_entity_id(None) is None
        assert normalize_entity_id(float("nan")) is None
        assert normalize_entity_id(np.nan) is None
        assert normalize_entity_id(pd.NA) is None
        assert normalize_entity_id("") is None
        assert normalize_entity_id("   ") is None

    def test_normalize_entity_id_preserves_valid_ids(self):
        assert normalize_entity_id("abc123") == "abc123"
        assert normalize_entity_id("  abc123  ") == "abc123"
        assert normalize_entity_id(123) == "123"

    def test_apply_column_aliases(self):
        identity = ManifestIdentity(column_aliases={"record_id": "entity_id"})
        df = pd.DataFrame({"record_id": ["p1"], "batch": [1]})
        out = apply_column_aliases(df, identity)
        assert "entity_id" in out.columns
        assert "record_id" not in out.columns

    def test_manifest_preserves_missing_entity_id(self):
        df = pd.DataFrame({
            "entity_id": ["p1", None, np.nan, "p2", pd.NA],
            "batch": [1, 1, 1, 1, 1],
            "slot": [None, None, None, None, None],
        })
        manifest = DatasetManifest(df)

        entity_ids = manifest.df["entity_id"]
        assert entity_ids.iloc[0] == "p1"
        assert entity_ids.iloc[1] is None or pd.isna(entity_ids.iloc[1])
        assert entity_ids.iloc[3] == "p2"

        assert not any(
            str(v).lower() == "nan" for v in entity_ids if v is not None and not pd.isna(v)
        )

    def test_manifest_no_id_collapse(self):
        df = pd.DataFrame({
            "entity_id": [None, None, None, "p1", "p2"],
            "batch": [1, 2, 3, 1, 1],
            "slot": [None, None, None, None, None],
        })
        manifest = DatasetManifest(df)

        entity_ids = manifest.df["entity_id"]
        assert entity_ids.isna().sum() == 3
        nan_string_count = (entity_ids.astype(str).str.lower() == "nan").sum()
        assert nan_string_count == 0
