"""Copy stage outputs to experiment export tree for downstream consumers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from plinth.dataset.structures import MetadataLedger

logger = logging.getLogger(__name__)


class ExportEngine:
    def export_stage_output(
        self,
        experiment_dir: Path,
        stage_output_dir: Path,
        stage_name: str,
        stage_dir_name: str,
    ) -> Path:
        export_root = experiment_dir / "export"
        export_root.mkdir(parents=True, exist_ok=True)
        export_path = export_root / stage_dir_name

        if export_path.exists():
            shutil.rmtree(export_path)

        shutil.copytree(stage_output_dir, export_path)
        logger.info(f"  [Export] {stage_name} -> {export_path}")

        ledger_path = stage_output_dir / "metadata_ledger.yaml"
        if ledger_path.exists():
            ledger = MetadataLedger.from_yaml(ledger_path)
            if ledger.entries:
                last = ledger.entries[-1]
                last.params = dict(last.params)
                last.params["exported_to"] = str(export_path)
                ledger.to_yaml(ledger_path)

        return export_path
