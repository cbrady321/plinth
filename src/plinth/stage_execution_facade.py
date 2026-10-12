"""Dispatch block-level stage execution to typical or exceptional lifecycle executors."""

from __future__ import annotations

from typing import Any

from plinth.context import StageContext
from plinth.registry import StageRegistry


class StageExecutionFacade:
    def run(
        self,
        stage_name: str,
        stage: Any,
        context: StageContext,
        *,
        arming_hash: str = "",
    ) -> None:
        if StageRegistry.get_mode(stage_name) == "exceptional":
            from plinth.runtime.exceptional_executor import ExceptionalStageExecutor

            ExceptionalStageExecutor().run(stage, context, arming_hash=arming_hash)
            return

        from plinth.runtime.executor import TypicalStageExecutor

        TypicalStageExecutor().run(stage, context, arming_hash=arming_hash)
