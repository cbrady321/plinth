"""Location-code helpers with no block dependencies."""

from __future__ import annotations

from typing import Optional, Union


def build_location_code(prefix: Union[int, str], parent_code: str = "") -> str:
    if isinstance(prefix, int):
        return parent_code + f"{prefix:02d}"
    return parent_code + str(prefix)


def directory_name(
    block_name: str,
    prefix: Optional[Union[int, str]],
    location_code: str = "",
) -> str:
    if location_code:
        return f"{location_code}_{block_name}"
    if isinstance(prefix, int):
        return f"{prefix:02d}_{block_name}"
    if isinstance(prefix, str):
        return f"{prefix}_{block_name}"
    raise ValueError("Cannot derive directory name without prefix or location_code")
