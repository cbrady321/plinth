"""Stage parameter schema type.

Consumers define their own schemas and register them with
``StageRegistry.register_param_schema``; plinth ships none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageParamSchema:
    json_schema: dict[str, Any]

    def validate(self, params: dict[str, Any], path_prefix: str) -> list[str]:
        import jsonschema

        validator = jsonschema.Draft202012Validator(self.json_schema)
        errors: list[str] = []
        for error in sorted(validator.iter_errors(params), key=lambda e: list(e.absolute_path)):
            field_path = ".".join(str(segment) for segment in error.absolute_path)
            location = f"{path_prefix}.{field_path}" if field_path else path_prefix
            errors.append(f"{location}: {error.message}")
        return errors
