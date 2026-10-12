"""Library for working with numbered stage directories in experiment folders."""

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from plinth.address.resolver import NodeAddressResolver

logger = logging.getLogger(__name__)


@dataclass
class StageDataDirectory:
    """Represents a numbered stage directory in an experiment folder."""

    sequence_number: int
    stage_name: str
    directory_path: Path

    def __str__(self) -> str:
        return f"{self.sequence_number:02d}_{self.stage_name}"

    @property
    def directory_name(self) -> str:
        """Get the directory name (e.g., '01_clean')."""
        return f"{self.sequence_number:02d}_{self.stage_name}"


@dataclass
class BlockDirectory:
    """Represents a block directory (sequential or parallel) in an experiment folder."""

    location_code: str
    block_name: str
    is_parallel: bool
    directory_path: Path

    def __str__(self) -> str:
        return f"{self.location_code}_{self.block_name}"

    @property
    def directory_name(self) -> str:
        """Get the directory name (e.g., '05_transform' or '06a_branch_a')."""
        return f"{self.location_code}_{self.block_name}"

    @property
    def name(self) -> str:
        """Get the directory name (alias for directory_name for compatibility)."""
        return self.directory_name


class StageDirectoryManager:
    """Manages numbered stage directories in experiment folders."""

    # Regex pattern to match numbered stage directories: 01_stage_name, 02_another_stage, etc.
    STAGE_DIR_PATTERN = re.compile(r"^(\d{2})_(.+)$")
    # Regex pattern to match alpha-prefixed directories: a_branch_name, b_another_branch, etc.
    ALPHA_DIR_PATTERN = re.compile(r"^([a-z])_(.+)$")
    # Regex pattern to match location code directories: 05_transform, 06a_branch_a, 06a01_stagename, etc.
    # Pattern: two digits, optionally followed by (letter + two digits) repeated, optionally ending with a letter
    LOCATION_CODE_PATTERN = re.compile(r"^(\d{2}(?:[a-z]\d{2})*[a-z]?)_(.+)$")

    def __init__(self, experiment_dir: Path):
        """
        Initialize with an experiment directory.

        Args:
            experiment_dir: Path to the experiment directory (e.g., data/experiment_name/)
        """
        self.experiment_dir = Path(experiment_dir)
        self._resolver = NodeAddressResolver()
        self._stage_directories: List[StageDataDirectory] = []
        self._block_directories: List[BlockDirectory] = []
        self._parse_existing_directories()

    @classmethod
    def parse_directory_name(cls, directory_name: str) -> Optional[Tuple[str, str]]:
        resolver = NodeAddressResolver()
        parsed = resolver.match_directory(directory_name)
        if parsed:
            return parsed
        numbered_match = cls.STAGE_DIR_PATTERN.match(directory_name)
        if numbered_match:
            return numbered_match.group(1), numbered_match.group(2)
        alpha_match = cls.ALPHA_DIR_PATTERN.match(directory_name)
        if alpha_match:
            return alpha_match.group(1), alpha_match.group(2)
        return None

    def _parse_existing_directories(self) -> None:
        """Parse existing stage and block directories in the experiment folder."""
        if not self.experiment_dir.exists():
            logger.debug(f"Experiment directory does not exist: {self.experiment_dir}")
            return

        self._stage_directories.clear()
        self._block_directories.clear()

        for item in self.experiment_dir.iterdir():
            if not item.is_dir():
                continue

            # Skip raw and dataset directories (shouldn't be in experiment dir, but skip for safety)
            if item.name in ("raw", "dataset"):
                continue

            parsed = self.parse_directory_name(item.name)
            if parsed:
                location_code, name_part = parsed
                if location_code.isdigit() and len(location_code) == 2:
                    stage_dir = StageDataDirectory(
                        sequence_number=int(location_code),
                        stage_name=name_part,
                        directory_path=item,
                    )
                    self._stage_directories.append(stage_dir)
                else:
                    is_parallel = location_code[-1].isalpha() if location_code else False
                    block_dir = BlockDirectory(
                        location_code=location_code,
                        block_name=name_part,
                        is_parallel=is_parallel,
                        directory_path=item,
                    )
                    self._block_directories.append(block_dir)
                continue

            logger.warning(
                "Skipping unparseable experiment directory (refuse-not-delete): %s",
                item.name,
            )

        # Sort by sequence number/prefix
        self._stage_directories.sort(key=lambda x: x.sequence_number)
        # Sort block directories by location code (lexicographically)
        self._block_directories.sort(key=lambda x: x.location_code)

        logger.debug(
            "Found %s stage directories and %s block directories in %s",
            len(self._stage_directories),
            len(self._block_directories),
            self.experiment_dir,
        )
        for stage_dir in self._stage_directories:
            logger.debug(f"  Stage: {stage_dir}")
        for block_dir in self._block_directories:
            logger.debug(f"  Block: {block_dir}")

    @property
    def stage_directories(self) -> List[StageDataDirectory]:
        """Get ordered list of stage directories."""
        return self._stage_directories.copy()

    @property
    def block_directories(self) -> List[BlockDirectory]:
        """Get ordered list of block directories."""
        return self._block_directories.copy()

    def get_stage_by_name(self, stage_name: str) -> Optional[StageDataDirectory]:
        """Find stage directory by stage name."""
        for stage_dir in self._stage_directories:
            if stage_dir.stage_name == stage_name:
                return stage_dir
        return None

    def get_stage_by_sequence(self, sequence_number: int) -> Optional[StageDataDirectory]:
        """Find stage directory by sequence number."""
        for stage_dir in self._stage_directories:
            if stage_dir.sequence_number == sequence_number:
                return stage_dir
        return None

    def get_block_by_name(self, block_name: str) -> Optional[BlockDirectory]:
        """Find block directory by block name."""
        for block_dir in self._block_directories:
            if block_dir.block_name == block_name:
                return block_dir
        return None

    def get_parallel_outputs(self, block_dir: Path) -> List[Path]:
        """
        Find all parallel branch outputs within a block directory.

        Args:
            block_dir: Path to the block directory

        Returns:
            List of paths to parallel branch output directories
        """
        if not block_dir.exists() or not block_dir.is_dir():
            return []

        parallel_outputs = []
        for item in block_dir.iterdir():
            if item.is_dir():
                # Check if it's an alpha-prefixed directory (parallel branch)
                alpha_match = self.ALPHA_DIR_PATTERN.match(item.name)
                if alpha_match:
                    parallel_outputs.append(item)

        return sorted(parallel_outputs)

    def get_next_sequence_number(self) -> int:
        """Get the next available sequence number."""
        if not self._stage_directories:
            return 1

        max_sequence = max(stage_dir.sequence_number for stage_dir in self._stage_directories)
        return max_sequence + 1

    def create_stage_directory(self, stage_name: str, sequence_number: Optional[int] = None) -> StageDataDirectory:
        """
        Create a new stage directory.

        Args:
            stage_name: Name of the stage
            sequence_number: Optional sequence number (auto-assigned if not provided)

        Returns:
            StageDataDirectory object for the created directory
        """
        if sequence_number is None:
            sequence_number = self.get_next_sequence_number()

        stage_dir = StageDataDirectory(
            sequence_number=sequence_number,
            stage_name=stage_name,
            directory_path=self.experiment_dir / f"{sequence_number:02d}_{stage_name}",
        )

        # Create the directory
        stage_dir.directory_path.mkdir(parents=True, exist_ok=True)

        # Add to our list and re-sort
        self._stage_directories.append(stage_dir)
        self._stage_directories.sort(key=lambda x: x.sequence_number)

        logger.info(f"Created stage directory: {stage_dir}")
        return stage_dir

    def create_block_directory(
        self, block_name: str, is_parallel: bool, location_code: Optional[str] = None
    ) -> BlockDirectory:
        """
        Create a new block directory.

        Args:
            block_name: Name of the block
            is_parallel: Whether this is a parallel block
            location_code: Optional location code (auto-assigned if not provided)

        Returns:
            BlockDirectory object for the created directory
        """
        if location_code is None:
            # Auto-assignment is not recommended with location codes
            # Location codes should be generated by the DAG execution
            raise ValueError("location_code must be provided when creating block directories")

        # Create directory name
        dir_name = f"{location_code}_{block_name}"

        block_dir = BlockDirectory(
            location_code=location_code,
            block_name=block_name,
            is_parallel=is_parallel,
            directory_path=self.experiment_dir / dir_name,
        )

        # Create the directory
        block_dir.directory_path.mkdir(parents=True, exist_ok=True)

        # Add to our list and re-sort
        self._block_directories.append(block_dir)
        self._block_directories.sort(key=lambda x: x.location_code)

        logger.info(f"Created block directory: {block_dir}")
        return block_dir

    def delete_stage_directories_from(
        self, start_stage_name: str, last_stage_name: Optional[str] = None
    ) -> List[StageDataDirectory]:
        """
        Delete stage directories from start_stage_name to the end.

        Args:
            start_stage_name: Name of the stage to start deletion from
            last_stage_name: Name of the last stage to delete (inclusive). If None, deletes to the end.

        Returns:
            List of deleted StageDataDirectory objects
        """
        # Find start stage
        start_stage = self.get_stage_by_name(start_stage_name)
        if not start_stage:
            logger.warning(f"Start stage '{start_stage_name}' not found in experiment directory")
            return []

        # Find last stage
        last_stage = None
        if last_stage_name:
            last_stage = self.get_stage_by_name(last_stage_name)
            if not last_stage:
                logger.warning(f"Last stage '{last_stage_name}' not found in experiment directory")
                return []

        # Collect stages to delete
        stages_to_delete = []
        for stage_dir in self._stage_directories:
            if stage_dir.sequence_number >= start_stage.sequence_number:
                if last_stage is None or stage_dir.sequence_number <= last_stage.sequence_number:
                    stages_to_delete.append(stage_dir)

        # Delete directories and remove from list
        deleted_stages = []
        for stage_dir in stages_to_delete:
            if stage_dir.directory_path.exists():
                logger.info(f"Deleting stage directory: {stage_dir}")
                shutil.rmtree(stage_dir.directory_path)
                deleted_stages.append(stage_dir)
            else:
                logger.warning(f"Stage directory does not exist: {stage_dir.directory_path}")

        # Remove from our list
        for stage_dir in deleted_stages:
            self._stage_directories.remove(stage_dir)

        logger.info(f"Deleted {len(deleted_stages)} stage directories")
        return deleted_stages

    def delete_block_directory(self, block_path: Path, *, strict: bool = False) -> bool:
        """
        Delete a block directory and all its contents.

        Args:
            block_path: Path to the block directory to delete
            strict: When True, refuse deletion if directory name is not parseable

        Returns:
            True if deletion was successful, False otherwise
        """
        if not block_path.exists():
            logger.warning(f"Block directory does not exist: {block_path}")
            return False

        if strict:
            try:
                block_path.relative_to(self.experiment_dir)
            except ValueError:
                logger.error(
                    "Refusing to delete path outside experiment directory: %s",
                    block_path,
                )
                return False
            if self.parse_directory_name(block_path.name) is None:
                logger.error(
                    "Refusing to delete unparseable directory name: %s",
                    block_path.name,
                )
                return False

        try:
            shutil.rmtree(block_path)
            logger.info(f"Deleted block directory: {block_path}")

            # Remove from our lists
            self._block_directories = [bd for bd in self._block_directories if bd.directory_path != block_path]
            return True
        except Exception as e:
            logger.error(f"Failed to delete block directory {block_path}: {e}")
            return False

    def get_stage_chain(self, start_stage_name: str, end_stage_name: Optional[str] = None) -> List[StageDataDirectory]:
        """
        Get ordered list of stage directories from start_stage_name to end_stage_name.

        Args:
            start_stage_name: Name of the stage to start from
            end_stage_name: Name of the stage to end at (inclusive). If None, goes to the end.

        Returns:
            List of StageDataDirectory objects in sequence order
        """
        # Find start stage
        start_stage = self.get_stage_by_name(start_stage_name)
        if not start_stage:
            logger.warning(f"Start stage '{start_stage_name}' not found")
            return []

        # Find end stage
        end_stage = None
        if end_stage_name:
            end_stage = self.get_stage_by_name(end_stage_name)
            if not end_stage:
                logger.warning(f"End stage '{end_stage_name}' not found")
                return []

        # Collect stages in range
        chain = []
        for stage_dir in self._stage_directories:
            if stage_dir.sequence_number >= start_stage.sequence_number:
                if end_stage is None or stage_dir.sequence_number <= end_stage.sequence_number:
                    chain.append(stage_dir)

        return chain

    def get_input_directory_for_stage(self, stage_name: str) -> Optional[Path]:
        """
        Get the input directory for a given stage (output of previous stage).

        Args:
            stage_name: Name of the stage

        Returns:
            Path to input directory, or None if stage not found or is first stage
        """
        stage = self.get_stage_by_name(stage_name)
        if not stage:
            return None

        # If this is the first stage, return None (no previous stage output)
        if stage.sequence_number == 1:
            return None

        # Find the previous stage
        previous_stage = self.get_stage_by_sequence(stage.sequence_number - 1)
        if previous_stage:
            return previous_stage.directory_path

        return None

    def get_output_directory_for_stage(self, stage_name: str) -> Path:
        """
        Get the output directory for a given stage.

        Args:
            stage_name: Name of the stage

        Returns:
            Path to output directory
        """
        stage = self.get_stage_by_name(stage_name)
        if stage:
            return stage.directory_path

        # If stage doesn't exist, create it
        return self.create_stage_directory(stage_name).directory_path

    def list_stage_names(self) -> List[str]:
        """Get list of stage names in sequence order."""
        return [stage_dir.stage_name for stage_dir in self._stage_directories]

    def __str__(self) -> str:
        """String representation of the stage directory manager."""
        if not self._stage_directories:
            return f"StageDirectoryManager({self.experiment_dir}) - No stages"

        stage_list = " → ".join(str(stage_dir) for stage_dir in self._stage_directories)
        return f"StageDirectoryManager({self.experiment_dir}) - {stage_list}"
