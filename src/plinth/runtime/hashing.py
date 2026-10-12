"""Directory and parameter hashing for ledger provenance.

A directory hash covers everything a stage directory holds except the ledger itself:

- each ``manifest.csv`` as a canonical row digest (row order, column order and the
  location of the file-pointer column do not matter; cell values do),
- each ``dataset_schema.yaml`` as its parsed content (YAML formatting does not matter),
- every other file as its streamed content digest,

each keyed by its path relative to the directory, so renaming or re-pointing a file changes the
hash. Directories whose rows carry no files still hash their row data.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from plinth.dataset.manifest_rows import normalize_manifest_rows

logger = logging.getLogger(__name__)

_LEDGER_FILE = "metadata_ledger.yaml"
_MANIFEST_FILE = "manifest.csv"
_SCHEMA_FILE = "dataset_schema.yaml"
_CHUNK_SIZE = 1 << 20


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _stream_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_digest(path: Path) -> str:
    if path.stat().st_size == 0:
        return hashlib.sha256(_canonical_json([])).hexdigest()
    try:
        rows = normalize_manifest_rows(path)
    except Exception as e:
        logger.warning(f"Could not parse {path} as a manifest; hashing raw content: {e}")
        return _stream_digest(path)
    return hashlib.sha256(_canonical_json(list(rows))).hexdigest()


def _schema_digest(path: Path) -> str:
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not parse {path} as YAML; hashing raw content: {e}")
        return _stream_digest(path)
    return hashlib.sha256(_canonical_json(data)).hexdigest()


def _file_digest(path: Path) -> str:
    if path.name == _MANIFEST_FILE:
        return "manifest:" + _manifest_digest(path)
    if path.name == _SCHEMA_FILE:
        return "schema:" + _schema_digest(path)
    return "file:" + _stream_digest(path)


def compute_directory_hash(directory: Path) -> str:
    if not directory.exists():
        return "0" * 64

    entries: list[tuple[str, str]] = []
    for file_path in directory.rglob("*"):
        if not file_path.is_file() or file_path.name == _LEDGER_FILE:
            continue
        relative = file_path.relative_to(directory).as_posix()
        try:
            entries.append((relative, _file_digest(file_path)))
        except Exception as e:
            logger.warning(f"Could not hash {file_path}: {e}")

    digest = hashlib.sha256()
    for relative, file_digest in sorted(entries):
        digest.update(_canonical_json([relative, file_digest]))
        digest.update(b"\n")
    return digest.hexdigest()


def compute_params_hash(config: dict[str, Any]) -> str:
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()
