"""
Pattern Operations for KATO
Handles CRUD operations for patterns including learning, retrieval, update, and deletion.
Extracted from KatoProcessor for better modularity.
"""

import logging
from typing import Any, Optional

from kato.exceptions import LearningError, PatternProcessingError, ResourceNotFoundError, ValidationError

logger = logging.getLogger('kato.workers.pattern_operations')


class PatternOperations:
    """
    Manages pattern CRUD operations for KATO.

    This class handles:
    - Pattern learning and creation
    - Pattern retrieval by ID
    - Pattern updates (frequency, emotives)
    - Pattern deletion
    - Vector retrieval
    """

    def __init__(self, pattern_processor, vector_processor, memory_manager):
        """
        Initialize pattern operations with references to processors.

        Args:
            pattern_processor: Reference to pattern processor for pattern operations
            vector_processor: Reference to vector processor for vector operations
            memory_manager: Reference to memory manager for state management
        """
        self.pattern_processor = pattern_processor
        self.vector_processor = vector_processor
        self.memory_manager = memory_manager

        # Quick access to knowledge base
        self.knowledge = pattern_processor.superkb.knowledge
        self.patterns_kb = pattern_processor.superkb.patterns_kb
        self.predictions_kb = self.knowledge.predictions_kb

        logger.debug("PatternOperations initialized")

    def learn_pattern(self, keep_tail=False, keep_stm_for_rolling=False) -> str:
        """
        Learn a new pattern from current STM.

        Creates a pattern from the current short-term memory state.
        The pattern is stored in both RAM (for fast search) and database (for persistence).

        Args:
            keep_tail: If True, keeps the last event in STM after learning (for auto-learning)
            keep_stm_for_rolling: If True, preserves STM for rolling window mode (new feature)

        Returns:
            Pattern name in format "PTRN|<hash>" if pattern was created,
            empty string if STM was empty or had only one event

        Raises:
            LearningError: If pattern learning fails
        """
        try:
            # Save tail event if needed BEFORE learning (which normally clears STM)
            tail_event = None

            if keep_tail and not keep_stm_for_rolling:
                # For tail mode: only save the last event
                stm_state = self.memory_manager.get_stm_state()
                if len(stm_state) > 1:
                    tail_event = stm_state[-1]

            # Learn vectors first (if any)
            self.vector_processor.learn()

            # Learn pattern from STM (this clears STM)
            pattern_name = self.pattern_processor.learn()

            # Handle STM restoration based on mode
            if keep_stm_for_rolling:
                # Rolling mode: DON'T restore full STM - that's handled by maintain_rolling_window
                # The STM has already been cleared by learn(), which is correct for rolling mode
                logger.debug("Rolling mode: STM cleared after learning, will be maintained by rolling window logic")
            elif tail_event:
                # Tail mode: only restore the last event
                self.memory_manager.set_stm_tail_context(tail_event)

            if pattern_name:
                full_name = f"PTRN|{pattern_name}"
                logger.info(f"Learned new pattern: {full_name}")
                return full_name

            # Return empty string for empty/single patterns (no pattern created)
            logger.debug("No pattern learned (STM empty or single event)")
            return ""

        except Exception as e:
            stm_state = self.memory_manager.get_stm_state()
            raise LearningError(
                f"Failed to learn pattern: {str(e)}",
                stm_state=stm_state,
                auto_learn=False
            )

    def get_pattern(self, pattern_id: str) -> dict[str, Any]:
        """
        Retrieve pattern information by pattern ID.

        Pattern IDs can be provided with or without the PTRN| prefix.
        MongoDB stores just the hash, so we strip the prefix before querying.

        Args:
            pattern_id: Pattern ID (with or without PTRN| prefix)

        Returns:
            Dictionary containing:
                - status: 'okay' or 'error'
                - pattern: Pattern data if found
                - message: Error message if not found

        Raises:
            PatternProcessingError: If pattern retrieval fails
        """
        try:
            # Strip PTRN| prefix if present for MongoDB query
            if pattern_id.startswith('PTRN|'):
                clean_name = pattern_id[5:]  # Remove 'PTRN|'
            else:
                clean_name = pattern_id

            # Query MongoDB with clean hash
            pattern = self.pattern_processor.superkb.getPattern(clean_name)

            if pattern is not None:
                # Remove MongoDB _id for JSON serialization
                if '_id' in pattern:
                    pattern.pop('_id')

                # Add PTRN| prefix to name field for consistency
                if 'name' in pattern and not pattern['name'].startswith('PTRN|'):
                    pattern['name'] = f"PTRN|{pattern['name']}"

                logger.debug(f"Retrieved pattern: {pattern_id}")
                return {'status': 'okay', 'pattern': pattern}
            else:
                logger.warning(f"Pattern not found: {pattern_id}")
                return {
                    'status': 'error',
                    'message': f'Pattern {pattern_id} not found'
                }

        except Exception as e:
            raise PatternProcessingError(
                f"Failed to retrieve pattern {pattern_id}: {str(e)}",
                pattern_name=pattern_id
            )

    def delete_pattern(self, name: str) -> str:
        """
        Delete pattern with the given name from both RAM and database.

        Args:
            name: Pattern name (hash without PTRN| prefix)

        Returns:
            'deleted' on success

        Raises:
            ResourceNotFoundError: If pattern not found
            PatternProcessingError: If deletion fails
        """
        try:
            # Strip PTRN| prefix if present
            if name.startswith('PTRN|'):
                clean_name = name[5:]
            else:
                clean_name = name

            # Delete from pattern processor (RAM and DB)
            result = self.pattern_processor.delete_pattern(clean_name)

            logger.info(f"Deleted pattern: {name}")
            return result

        except Exception as e:
            if "Unable to find" in str(e):
                raise ResourceNotFoundError(
                    f"Pattern {name} not found",
                    resource_type="pattern",
                    resource_id=name
                )
            else:
                raise PatternProcessingError(
                    f"Failed to delete pattern {name}: {str(e)}",
                    pattern_name=name
                )

    def update_pattern(self, name: str, frequency: Optional[int] = None,
                      emotives: Optional[dict[str, list[float]]] = None) -> dict[str, Any]:
        """
        Update the frequency and/or emotives of a pattern.

        Args:
            name: Pattern name (hash without PTRN| prefix)
            frequency: New frequency value (optional)
            emotives: New emotives values (optional)

        Returns:
            Updated pattern document

        Raises:
            ValidationError: If update parameters are invalid
            PatternProcessingError: If update fails
        """
        try:
            # Strip PTRN| prefix if present
            if name.startswith('PTRN|'):
                clean_name = name[5:]
            else:
                clean_name = name

            # Validate parameters
            if frequency is not None and frequency < 0:
                raise ValidationError(
                    "Pattern frequency cannot be negative",
                    field_name="frequency",
                    field_value=frequency,
                    validation_rule="Must be >= 0"
                )

            # Update pattern
            result = self.pattern_processor.update_pattern(clean_name, frequency, emotives)

            logger.info(f"Updated pattern: {name} (frequency={frequency}, "
                       f"emotives={len(emotives) if emotives else 0} dimensions)")
            return result

        except ValidationError:
            raise
        except Exception as e:
            raise PatternProcessingError(
                f"Failed to update pattern {name}: {str(e)}",
                pattern_name=name
            )

    def get_vector(self, name: str) -> Optional[list[float]]:
        """
        Retrieve vector values by vector name.

        Args:
            name: Vector name (e.g., 'VCTR|hash')

        Returns:
            Vector values as list of floats, or None if not found

        Raises:
            ResourceNotFoundError: If vector not found
        """
        try:
            vector = self.pattern_processor.superkb.getVector(name)

            if vector is None:
                raise ResourceNotFoundError(
                    f"Vector {name} not found",
                    resource_type="vector",
                    resource_id=name
                )

            logger.debug(f"Retrieved vector: {name}")
            return vector

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve vector {name}: {str(e)}")
            raise ResourceNotFoundError(
                f"Failed to retrieve vector {name}: {str(e)}",
                resource_type="vector",
                resource_id=name
            )

    def get_predictions(self, unique_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Retrieve predictions for a specific observation ID.

        If no ID provided, returns the most recent predictions from memory.
        Otherwise queries the database for stored predictions.

        Args:
            unique_id: Observation unique ID (optional)

        Returns:
            List of prediction dictionaries
        """
        predictions = []

        if not unique_id:
            # Return current predictions from memory
            predictions = self.pattern_processor.predictions
        else:
            # Query database for predictions by unique_id
            pred_results = self.predictions_kb.find({'unique_id': unique_id})
            for pred in pred_results:
                if '_id' in pred:
                    pred.pop('_id')
                predictions.append(pred)

        logger.debug(f"Retrieved {len(predictions)} predictions for "
                    f"{'current state' if not unique_id else f'ID {unique_id}'}")
        return predictions

    def get_pattern_count(self) -> int:
        """
        Get the total count of patterns in the database.

        Returns:
            Number of patterns in database
        """
        try:
            count = self.patterns_kb.count_documents({})
            logger.debug(f"Pattern count: {count}")
            return count
        except Exception as e:
            logger.error(f"Failed to get pattern count: {str(e)}")
            return 0
