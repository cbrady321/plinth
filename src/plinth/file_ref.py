"""File content or path handover for stage artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileRef:
    extension: str
    content: Optional[bytes] = None
    source_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.content is None and self.source_path is None:
            raise ValueError("FileRef must provide either 'content' or 'source_path'")
        if self.content is not None and self.source_path is not None:
            raise ValueError("FileRef cannot provide both 'content' and 'source_path'")
