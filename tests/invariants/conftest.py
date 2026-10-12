"""Fixtures for the invariant suite: the golden and hermetic stages, and a throwaway registry."""

from __future__ import annotations

from typing import Iterator

import pytest

from plinth.registry import StageRegistry

# Class-level tables on StageRegistry that a test may mutate.
_REGISTRY_TABLES = ("_stages", "_modes", "_exceptional_metadata", "_param_schemas")


@pytest.fixture(scope="session", autouse=True)
def golden_and_hermetic_stages() -> Iterator[None]:
    """Register every stage the invariant tests refer to by name, once per session."""
    from tests import hermetic_stages  # noqa: F401  (registers on import)
    from tests.golden import golden_stages  # noqa: F401  (registers on import)
    from tests.hermetic_param_schemas import register_hermetic_param_schemas

    register_hermetic_param_schemas()
    yield


@pytest.fixture
def isolated_registry() -> Iterator[None]:
    """Give the test an empty registry, then put back exactly what was registered before."""
    snapshot = {name: dict(getattr(StageRegistry, name)) for name in _REGISTRY_TABLES}
    StageRegistry.clear()
    try:
        yield
    finally:
        StageRegistry.clear()
        for name, entries in snapshot.items():
            getattr(StageRegistry, name).update(entries)
