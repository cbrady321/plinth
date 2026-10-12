"""Hermetic param schema for the test-only ``allowlist_filter`` stage."""

from __future__ import annotations

from plinth.param_schemas import StageParamSchema
from plinth.registry import StageRegistry

ALLOWLIST_FILTER_PARAMS = StageParamSchema(
    {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "allow": {
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"},
                ]
            },
            "case_insensitive": {"type": "boolean"},
        },
    }
)


def register_hermetic_param_schemas() -> None:
    StageRegistry.register_param_schema("allowlist_filter", ALLOWLIST_FILTER_PARAMS)
