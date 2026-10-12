"""Tabular records: validate, enrich and aggregate rows that point at no files at all.

Each input row is one order line from a CSV export. There is no file column — every row reaches
``process_file`` with ``input_path == NO_SOURCE_FILE`` and nothing is copied on disk. The raw export
names the customer column ``client``; the schema's ``column_aliases`` renames it on ingest. The
pipeline

1. ``validate_orders``  filters out lines with a non-positive quantity or a missing price,
2. ``price_orders``     converts every line to a common currency (``fx_rates`` param),
3. ``customer_totals``  collapses order lines into one row per customer.

Run it::

    python examples/tabular_records.py [workdir]

The same shape fits event logs, survey responses, sensor readings or feature tables.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.media import NO_SOURCE_FILE
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.experiment_launcher import ExperimentLauncher
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome

SCHEMA = DatasetSchema(
    identity=ManifestIdentity(
        entity_key="customer_id",
        hierarchy_keys=["order_id"],
        column_aliases={"client": "customer_id"},
    ),
)

# --------------------------------------------------------------------------- stages


class ValidateOrdersStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"quantity", "unit_price"},
            filters_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        assert input_path == NO_SOURCE_FILE  # tabular rows carry no file
        price = metadata.get("unit_price")
        if price is None or pd.isna(price) or float(metadata["quantity"]) <= 0:
            return StageOutcome.filter()
        return StageOutcome.update()


class PriceOrdersStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"quantity", "unit_price", "currency"},
            write_columns={"line_total": "float"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        rate = float(self.config["fx_rates"][metadata["currency"]])
        return StageOutcome.update(line_total=round(float(metadata["quantity"]) * float(metadata["unit_price"]) * rate, 2))


class CustomerTotalsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"customer_id", "line_total"},
            write_columns={"order_count": "int", "revenue": "float"},
            group_by=["customer_id"],
            aggregates_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_group(
        self, group_keys: Dict[str, Any], rows: List[Dict[str, Any]], input_dir: Path, output_dir: Path
    ) -> StageOutcome:
        return StageOutcome.aggregate(
            customer_id=group_keys["customer_id"],
            order_count=len({r["order_id"] for r in rows}),
            revenue=round(sum(float(r["line_total"]) for r in rows), 2),
        )


def register_stages() -> None:
    StageRegistry.register("validate_orders", mode="typical")(ValidateOrdersStage)
    StageRegistry.register("price_orders", mode="typical")(PriceOrdersStage)
    StageRegistry.register("customer_totals", mode="typical")(CustomerTotalsStage)


CONFIG = PipelineConfig(
    name="tabular_records",
    version="1.0",
    dag={
        "type": "sequential",
        "name": "root",
        "children": [
            {"type": "stage", "name": "validate_orders"},
            {"type": "stage", "name": "price_orders"},
            {"type": "stage", "name": "customer_totals"},
        ],
    },
    params={"price_orders": {"fx_rates": {"USD": 1.0, "EUR": 1.1}}},
)

# --------------------------------------------------------------------------- synthetic dataset


def build_dataset(root: Path) -> Path:
    """Write a raw order export (``client`` column, one bad line) plus ``dataset_schema.yaml``."""
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"client": "c1", "order_id": "o1", "quantity": 2, "unit_price": 10.0, "currency": "USD"},
            {"client": "c1", "order_id": "o2", "quantity": 1, "unit_price": 50.0, "currency": "EUR"},
            {"client": "c2", "order_id": "o3", "quantity": 3, "unit_price": 5.0, "currency": "USD"},
            {"client": "c2", "order_id": "o4", "quantity": 0, "unit_price": 99.0, "currency": "USD"},  # invalid
            {"client": "c3", "order_id": "o5", "quantity": 1, "unit_price": None, "currency": "USD"},  # invalid
        ]
    ).to_csv(manifest_csv_path(root), index=False)
    SCHEMA.to_yaml(dataset_schema_path(root))
    return root


# --------------------------------------------------------------------------- entry point


def main(workdir: Path) -> pd.DataFrame:
    register_stages()
    dataset = build_dataset(workdir / "data" / "pipeline" / "publish" / "dataset")
    result = ExperimentLauncher(workdir).run(CONFIG, "tabular_records", input_source=str(dataset))
    manifest = DatasetManifest.from_csv(manifest_csv_path(result.output_dir), schema=SCHEMA)
    print(manifest.df.to_string(index=False))
    print(f"\nRun directory: {result.output_dir}")
    return manifest.df


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plinth-tabular-")))
