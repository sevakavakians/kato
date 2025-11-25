"""
Memory Manager for KATO - STATELESS VERSION

Provides stateless helper functions for memory operations.
All functions take state as input and return new state as output.
No mutation of state - follows functional programming principles.

ARCHITECTURE: After v3.0 stateless refactor
- No instance variables for session state
- All methods are static or class methods
- State is passed as parameters
- State is returned as new objects (no mutation)
"""

import logging
from typing import Any, Optional

from kato.exceptions import MemoryOperationError
from kato.informatics.metrics import average_emotives

logger = logging.getLogger('kato.workers.memory_manager')


class MemoryManager:
    """
    Stateless memory operation helpers for KATO processor.

    This class provides pure functions for:
    - STM state transformations
    - Emotives processing and accumulation
    - Metadata processing and accumulation
    - Percept data construction

    All methods are stateless - they take state as input and return new state.
    No instance variables hold session-specific state.
    """

    def __init__(self, pattern_processor, vector_processor):
        """
        Initialize memory manager with references to LTM processors.

        Args:
            pattern_processor: Reference to pattern processor (for LTM operations only)
            vector_processor: Reference to vector processor (for LTM operations only)

        Note: These references are for LTM operations (shared by design).
              Session-specific state is NOT stored here.
        """
        self.pattern_processor = pattern_processor
        self.vector_processor = vector_processor
        logger.debug("MemoryManager initialized (stateless)")

    # =========================================================================
    # STATE CREATION AND RESET
    # =========================================================================

    @staticmethod
    def create_empty_state() -> dict[str, Any]:
        """
        Create an empty session state dictionary.

        Returns:
            Dictionary with all session state variables initialized to empty/zero
        """
        return {
            'symbols': [],
            'current_emotives': {},
            'emotives_accumulator': [],
            'metadata_accumulator': [],
            'last_command': "",
            'percept_data': {},
            'percept_data_vector': None,
            'time': 0
        }

    def clear_stm(self, pattern_processor) -> None:
        """
        Clear STM in pattern processor (LTM operation).

        This is a side effect operation that clears the pattern processor's STM.
        Does NOT clear session state - that should be done by caller.

        Args:
            pattern_processor: Pattern processor to clear STM from

        Raises:
            MemoryOperationError: If clearing fails
        """
        try:
            # Clear STM in pattern processor (LTM side effect)
            pattern_processor.clear_stm()

            # Also clear v_identified (pattern matching state)
            pattern_processor.v_identified = []

            logger.info("Pattern processor STM cleared successfully")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to clear STM: {str(e)}",
                memory_type="STM",
                operation="clear"
            )

    def clear_all_memory(self, pattern_processor, vector_processor) -> None:
        """
        Clear all memory (both STM and LTM) - SIDE EFFECT operation.

        This is a destructive operation that clears:
        - Short-term memory (STM) in pattern processor
        - Long-term memory (patterns in database)
        - Vector memory

        Session state should be reset by caller using create_empty_state().

        Args:
            pattern_processor: Pattern processor to clear
            vector_processor: Vector processor to clear

        Raises:
            MemoryOperationError: If clearing fails

        WARNING: This operation cannot be undone and will delete all learned patterns.
        """
        try:
            # Clear pattern processor memory (includes database operations)
            pattern_processor.superkb.clear_all_memory()
            pattern_processor.clear_all_memory()

            # Clear vector processor memory
            vector_processor.clear_all_memory()

            logger.info("All memory cleared successfully (STM and LTM)")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to clear all memory: {str(e)}",
                memory_type="ALL",
                operation="clear"
            )

    # =========================================================================
    # TIME OPERATIONS (Pure functions)
    # =========================================================================

    @staticmethod
    def increment_time(current_time: int) -> int:
        """
        Increment time counter.

        Args:
            current_time: Current time value

        Returns:
            New time value (current_time + 1)
        """
        return current_time + 1

    # =========================================================================
    # EMOTIVES OPERATIONS (Pure functions)
    # =========================================================================

    @staticmethod
    def process_emotives(
        emotives_accumulator: list[dict[str, float]],
        new_emotives: dict[str, float]
    ) -> tuple[list[dict[str, float]], dict[str, float]]:
        """
        Process and accumulate emotives data.

        Args:
            emotives_accumulator: Current list of accumulated emotives
            new_emotives: New emotives to add

        Returns:
            Tuple of:
            - Updated emotives_accumulator (with new_emotives appended)
            - current_emotives (averaged over all accumulated emotives)

        Raises:
            MemoryOperationError: If processing fails
        """
        try:
            if not new_emotives:
                # No new emotives, return unchanged
                current_avg = average_emotives(emotives_accumulator) if emotives_accumulator else {}
                return emotives_accumulator, current_avg

            # Create new accumulator with new emotives appended
            new_accumulator = emotives_accumulator.copy()
            new_accumulator.append(new_emotives)

            # Calculate average of all accumulated emotives
            current_avg = average_emotives(new_accumulator)

            return new_accumulator, current_avg

        except Exception as e:
            raise MemoryOperationError(
                f"Failed to process emotives: {str(e)}",
                memory_type="STM",
                operation="process_emotives",
                context={"emotives_count": len(new_emotives) if new_emotives else 0}
            )

    # =========================================================================
    # METADATA OPERATIONS (Pure functions)
    # =========================================================================

    @staticmethod
    def process_metadata(
        metadata_accumulator: list[dict[str, Any]],
        new_metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Process and accumulate metadata.

        Args:
            metadata_accumulator: Current list of accumulated metadata
            new_metadata: New metadata to add

        Returns:
            Updated metadata_accumulator (with new_metadata appended)

        Raises:
            MemoryOperationError: If processing fails
        """
        try:
            if not new_metadata:
                # No new metadata, return unchanged
                return metadata_accumulator

            # Create new accumulator with new metadata appended
            new_accumulator = metadata_accumulator.copy()
            new_accumulator.append(new_metadata)

            return new_accumulator

        except Exception as e:
            raise MemoryOperationError(
                f"Failed to process metadata: {str(e)}",
                memory_type="STM",
                operation="process_metadata",
                context={"metadata_keys": len(new_metadata) if new_metadata else 0}
            )

    # =========================================================================
    # PERCEPT DATA OPERATIONS (Pure functions)
    # =========================================================================

    @staticmethod
    def build_percept_data(
        strings: list[str],
        vectors: list[list[float]],
        emotives: dict[str, float],
        path: list[str],
        metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build percept data dictionary from observation components.

        Args:
            strings: String observations
            vectors: Vector observations
            emotives: Emotional values
            path: Processing path
            metadata: Additional metadata

        Returns:
            Percept data dictionary
        """
        return {
            'strings': strings,
            'vectors': vectors,
            'emotives': emotives,
            'path': path,
            'metadata': metadata
        }

    # =========================================================================
    # STM STATE OPERATIONS (Read operations)
    # =========================================================================

    @staticmethod
    def get_stm_from_pattern_processor(pattern_processor) -> list[list[str]]:
        """
        Get STM from pattern processor.

        This reads the current STM from the pattern processor.
        Note: In stateless architecture, STM should primarily live in SessionState,
        but pattern processor may maintain a working copy during processing.

        Args:
            pattern_processor: Pattern processor to read STM from

        Returns:
            Current STM as list of symbol lists
        """
        return list(pattern_processor.STM)

    @staticmethod
    def get_stm_length(stm: list[list[str]]) -> int:
        """
        Get the length of STM.

        Args:
            stm: Short-term memory as list of events

        Returns:
            Number of events in STM
        """
        return len(stm)

    def set_stm_in_pattern_processor(
        self,
        pattern_processor,
        stm: list[list[str]]
    ) -> None:
        """
        Set STM in pattern processor (side effect operation).

        This is used to load session STM into pattern processor for processing.
        After stateless refactor, this should only be called when loading
        session state into processor for a specific operation.

        Args:
            pattern_processor: Pattern processor to update
            stm: STM to set

        Raises:
            MemoryOperationError: If setting fails
        """
        try:
            pattern_processor.setSTM(stm)
            logger.debug(f"STM set in pattern processor ({len(stm)} events)")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to set STM in pattern processor: {str(e)}",
                memory_type="STM",
                operation="set_stm"
            )

    def set_stm_tail_context(
        self,
        pattern_processor,
        tail_event: list[str]
    ) -> None:
        """
        Set STM with a tail event for context continuity (side effect operation).

        Used during auto-learning to maintain context between learned patterns.

        Args:
            pattern_processor: Pattern processor to update
            tail_event: The last event to keep as context

        Raises:
            MemoryOperationError: If setting fails
        """
        try:
            pattern_processor.setSTM([tail_event])
            logger.debug(f"STM tail context set with {len(tail_event)} symbols")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to set STM tail context: {str(e)}",
                memory_type="STM",
                operation="set_tail_context"
            )

    # =========================================================================
    # SYMBOL OPERATIONS (Pure functions)
    # =========================================================================

    @staticmethod
    def add_symbols(
        current_symbols: list[str],
        new_symbols: list[str]
    ) -> list[str]:
        """
        Add new symbols to symbol list.

        Args:
            current_symbols: Current symbol list
            new_symbols: New symbols to add

        Returns:
            Updated symbol list (current_symbols + new_symbols)
        """
        result = current_symbols.copy()
        result.extend(new_symbols)
        return result

    @staticmethod
    def clear_symbols() -> list[str]:
        """
        Create empty symbol list.

        Returns:
            Empty list
        """
        return []
