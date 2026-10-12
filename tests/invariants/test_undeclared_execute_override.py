"""Only stages registered as exceptional may replace ``BaseStage.execute``."""

from __future__ import annotations

from plinth.base_stage import BaseStage
from plinth.registry import StageRegistry


def _overrides_execute(stage_class: type) -> bool:
    return any("execute" in vars(klass) for klass in stage_class.__mro__ if klass is not BaseStage and klass is not object)


def test_every_execute_override_is_registered_exceptional() -> None:
    # The session fixture in conftest.py has registered every golden and hermetic stage by now.
    offenders = sorted(
        name
        for name in StageRegistry.list_stages()
        if _overrides_execute(StageRegistry.get_stage(name)) and StageRegistry.get_mode(name) != "exceptional"
    )
    assert not offenders, f"typical stages overriding execute(): {offenders}"


def test_the_check_sees_exceptional_overrides() -> None:
    # Guard against a vacuous pass: the corpus does contain exceptional stages that override execute().
    exceptional = [name for name in StageRegistry.list_stages() if StageRegistry.get_mode(name) == "exceptional"]
    assert any(_overrides_execute(StageRegistry.get_stage(name)) for name in exceptional)
