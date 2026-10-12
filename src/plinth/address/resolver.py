"""Canonical node address derivation for DAG pipeline directories."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from plinth.address.codes import build_location_code, directory_name
from plinth.jsonpath_resolver import path_to_index_list

if TYPE_CHECKING:
    from plinth.blocks import Block

_VALID_LOCATION_CODE = re.compile(r"^(\d{2}(?:[a-z]\d{2})*[a-z]*|[a-z])$")


@dataclass(frozen=True)
class NodeAddress:
    location_code: str
    block_name: str
    directory_name: str


@dataclass
class _ResolveContext:
    config: Dict[str, Any]
    sequential_counter: List[int] = field(default_factory=lambda: [1])

    def next_branch_stage_num(self, parent_location_code: str) -> int:
        key = f"_branch_counters_{parent_location_code}"
        if key not in self.config:
            self.config[key] = [1]
        counter = self.config[key]
        num = int(counter[0])
        counter[0] = num + 1
        return num

    def next_sequential_num(self) -> int:
        num = self.sequential_counter[0]
        self.sequential_counter[0] += 1
        return num


class NodeAddressResolver:
    build_location_code = staticmethod(build_location_code)
    directory_name = staticmethod(directory_name)

    def resolve_at_index_path(
        self,
        dag_root: Block,
        index_path: List[int],
        config: Optional[Dict[str, Any]] = None,
    ) -> NodeAddress:
        from plinth.blocks import ParallelBlock, SequentialBlock, StageNode

        ctx = _ResolveContext(config=dict(config or {}))
        return self._resolve_walk(
            dag_root,
            index_path,
            prefix=1,
            parent_location_code="",
            ctx=ctx,
            SequentialBlock=SequentialBlock,
            ParallelBlock=ParallelBlock,
            StageNode=StageNode,
        )

    def resolve_from_jsonpath(
        self,
        dag_root: Block,
        jsonpath: str,
        root_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> NodeAddress:
        index_path = path_to_index_list(jsonpath, root_name)
        return self.resolve_at_index_path(dag_root, index_path, config=config)

    def child_prefix_for_cleanup(
        self,
        parent: Block,
        child: Block,
        child_idx: int,
    ) -> Union[int, str]:
        from plinth.blocks import ParallelBlock

        if isinstance(parent, ParallelBlock):
            return chr(ord("a") + child_idx)
        if isinstance(child, ParallelBlock):
            return child_idx + 1
        return child_idx + 1

    def match_directory(self, directory_name_str: str) -> Optional[tuple[str, str]]:
        if "_" not in directory_name_str:
            return None
        location_code, block_name = directory_name_str.split("_", 1)
        if not location_code or not block_name:
            return None
        if not _VALID_LOCATION_CODE.match(location_code):
            return None
        return location_code, block_name

    @staticmethod
    def _sequential_slots_consumed(
        block: Block,
        SequentialBlock: type,
        ParallelBlock: type,
    ) -> int:
        if isinstance(block, SequentialBlock):
            return 1 + sum(
                NodeAddressResolver._sequential_slots_consumed(child, SequentialBlock, ParallelBlock)
                for child in block.children
            )
        return 1

    def _resolve_walk(
        self,
        block: Block,
        index_path: List[int],
        prefix: Optional[Union[int, str]],
        parent_location_code: str,
        ctx: _ResolveContext,
        SequentialBlock: type,
        ParallelBlock: type,
        StageNode: type,
    ) -> NodeAddress:
        location_code = ""
        dir_name = ""

        if isinstance(block, SequentialBlock):
            if prefix and isinstance(prefix, str):
                location_code = build_location_code(prefix, parent_location_code)
                dir_name = directory_name(block.name, prefix, location_code)
            else:
                block_num = ctx.next_sequential_num()
                dir_name = f"{block_num:02d}_{block.name}"
        elif isinstance(block, ParallelBlock):
            if prefix is None:
                raise ValueError("Parallel blocks require a prefix")
            if isinstance(prefix, int):
                location_code = f"{prefix:02d}"
                dir_name = f"{prefix:02d}_{block.name}"
            else:
                location_code = build_location_code(prefix, parent_location_code)
                dir_name = directory_name(block.name, prefix, location_code)
        elif isinstance(block, StageNode):
            if prefix and isinstance(prefix, str):
                location_code = build_location_code(prefix, parent_location_code)
                dir_name = directory_name(block.name, prefix, location_code)
            elif parent_location_code:
                stage_num = ctx.next_branch_stage_num(parent_location_code)
                location_code = parent_location_code + f"{stage_num:02d}"
                dir_name = f"{location_code}_{block.name}"
            else:
                stage_num = ctx.next_sequential_num()
                dir_name = f"{stage_num:02d}_{block.name}"
        else:
            if isinstance(prefix, int):
                location_code = build_location_code(prefix, parent_location_code)
                dir_name = directory_name(block.name, prefix, location_code)
            elif isinstance(prefix, str):
                location_code = build_location_code(prefix, parent_location_code)
                dir_name = directory_name(block.name, prefix, location_code)
            else:
                stage_num = ctx.next_sequential_num()
                dir_name = f"{stage_num:02d}_{block.name}"

        if not index_path:
            return NodeAddress(
                location_code=location_code,
                block_name=block.name,
                directory_name=dir_name,
            )

        child_idx = index_path[0]
        child = block.children[child_idx]
        child_parent_code = parent_location_code

        if isinstance(block, SequentialBlock):
            if isinstance(child, ParallelBlock):
                child_prefix = ctx.next_sequential_num()
                child_parent_code = ""
                return self._resolve_walk(
                    child,
                    index_path[1:],
                    prefix=child_prefix,
                    parent_location_code=child_parent_code,
                    ctx=ctx,
                    SequentialBlock=SequentialBlock,
                    ParallelBlock=ParallelBlock,
                    StageNode=StageNode,
                )
            for sibling_idx in range(child_idx):
                ctx.sequential_counter[0] += self._sequential_slots_consumed(
                    block.children[sibling_idx],
                    SequentialBlock,
                    ParallelBlock,
                )
            return self._resolve_walk(
                child,
                index_path[1:],
                prefix=None,
                parent_location_code=location_code if location_code else "",
                ctx=ctx,
                SequentialBlock=SequentialBlock,
                ParallelBlock=ParallelBlock,
                StageNode=StageNode,
            )

        if isinstance(block, ParallelBlock):
            parallel_child_prefix: Union[int, str] = chr(ord("a") + child_idx)
            if isinstance(prefix, str) and parent_location_code:
                child_parent_code = location_code
            elif isinstance(prefix, int):
                child_parent_code = location_code
            else:
                child_parent_code = location_code
            return self._resolve_walk(
                child,
                index_path[1:],
                prefix=parallel_child_prefix,
                parent_location_code=child_parent_code,
                ctx=ctx,
                SequentialBlock=SequentialBlock,
                ParallelBlock=ParallelBlock,
                StageNode=StageNode,
            )

        child_prefix = child_idx + 1
        return self._resolve_walk(
            child,
            index_path[1:],
            prefix=child_prefix,
            parent_location_code=child_parent_code,
            ctx=ctx,
            SequentialBlock=SequentialBlock,
            ParallelBlock=ParallelBlock,
            StageNode=StageNode,
        )
