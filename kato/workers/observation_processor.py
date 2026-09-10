"""
Observation Processor for KATO
Handles processing of incoming observations including strings, vectors, and emotives.
Extracted from KatoProcessor for better modularity.
"""

import logging
from typing import Any, Optional

from kato.exceptions import ObservationError, ValidationError

logger = logging.getLogger('kato.workers.observation_processor')


class ObservationProcessor:
    """
    Processes incoming observations for KATO.

    This class handles:
    - String symbol processing
    - Vector processing through vector processor
    - Emotives processing
    - Auto-learning triggers
    - Observation validation
    """

    def __init__(self, vector_processor, pattern_processor, memory_manager,
                 pattern_operations, sort_symbols, max_pattern_length, process_predictions=True):
        """
        Initialize observation processor with references to other components.

        Args:
            vector_processor: Reference to vector processor for vector operations
            pattern_processor: Reference to pattern processor for STM operations
            memory_manager: Reference to memory manager for state management
            pattern_operations: Reference to pattern operations for learning
            sort_symbols: Whether to sort symbols alphabetically
            max_pattern_length: Maximum pattern length for auto-learning
            process_predictions: Whether to compute predictions (default True)
        """
        self.vector_processor = vector_processor
        self.pattern_processor = pattern_processor
        self.memory_manager = memory_manager
        self.pattern_operations = pattern_operations

        # Get configuration passed in
        self.sort_symbols = sort_symbols
        self.max_pattern_length = max_pattern_length
        self.process_predictions = process_predictions

        # Processing lock for thread safety

        logger.debug("ObservationProcessor initialized")

    def validate_observation(self, data: dict[str, Any]) -> None:
        """
        Validate incoming observation data.

        Args:
            data: Observation data to validate

        Raises:
            ValidationError: If validation fails
        """
        # Check for required unique_id
        if 'unique_id' not in data or data['unique_id'] == '':
            raise ValidationError(
                "Observation must include a non-empty unique_id",
                field_name="unique_id",
                field_value=data.get('unique_id'),
                validation_rule="Required non-empty string"
            )

        # Validate strings if present
        if 'strings' in data and data['strings'] is not None:
            if not isinstance(data['strings'], list):
                raise ValidationError(
                    "Strings must be a list",
                    field_name="strings",
                    field_value=type(data['strings']).__name__,
                    validation_rule="Must be list type"
                )
            for i, s in enumerate(data['strings']):
                if not isinstance(s, str):
                    raise ValidationError(
                        f"String at index {i} must be a string",
                        field_name=f"strings[{i}]",
                        field_value=type(s).__name__,
                        validation_rule="Must be string type"
                    )

        # Validate vectors if present
        if 'vectors' in data and data['vectors'] is not None:
            if not isinstance(data['vectors'], list):
                raise ValidationError(
                    "Vectors must be a list",
                    field_name="vectors",
                    field_value=type(data['vectors']).__name__,
                    validation_rule="Must be list type"
                )
            for i, vector in enumerate(data['vectors']):
                if not isinstance(vector, list):
                    raise ValidationError(
                        f"Vector at index {i} must be a list",
                        field_name=f"vectors[{i}]",
                        field_value=type(vector).__name__,
                        validation_rule="Must be list type"
                    )
                if not all(isinstance(v, (int, float)) for v in vector):
                    raise ValidationError(
                        f"Vector at index {i} must contain only numbers",
                        field_name=f"vectors[{i}]",
                        validation_rule="Must contain int or float values"
                    )

        # Validate emotives if present
        if 'emotives' in data and data['emotives'] is not None:
            if not isinstance(data['emotives'], dict):
                raise ValidationError(
                    "Emotives must be a dictionary",
                    field_name="emotives",
                    field_value=type(data['emotives']).__name__,
                    validation_rule="Must be dict type"
                )
            for key, value in data['emotives'].items():
                if not isinstance(key, str):
                    raise ValidationError(
                        "Emotive key must be a string",
                        field_name=f"emotives[{key}]",
                        field_value=type(key).__name__,
                        validation_rule="Key must be string type"
                    )
                if not isinstance(value, (int, float)):
                    raise ValidationError(
                        f"Emotive value for '{key}' must be a number",
                        field_name=f"emotives[{key}]",
                        field_value=type(value).__name__,
                        validation_rule="Value must be int or float"
                    )

        # Validate metadata if present
        if 'metadata' in data and data['metadata'] is not None:
            if not isinstance(data['metadata'], dict):
                raise ValidationError(
                    "Metadata must be a dictionary",
                    field_name="metadata",
                    field_value=type(data['metadata']).__name__,
                    validation_rule="Must be dict type"
                )
            for key in data['metadata'].keys():
                if not isinstance(key, str):
                    raise ValidationError(
                        "Metadata key must be a string",
                        field_name=f"metadata[{key}]",
                        field_value=type(key).__name__,
                        validation_rule="Key must be string type"
                    )

    def process_vectors(self, vector_data: list[list[float]]) -> list[str]:
        """
        Process vectors through vector processor to get symbolic representations.

        Args:
            vector_data: List of vector embeddings

        Returns:
            List of vector-derived symbols (e.g., ['VCTR|hash1', 'VCTR|hash2'])

        Raises:
            VectorDimensionError: If vector dimensions are invalid
            ObservationError: If vector processing fails
        """
        try:
            if not vector_data:
                return []

            # Process vectors to get symbolic names
            symbols = self.vector_processor.process(vector_data)

            # Sort if configured
            if symbols and self.sort_symbols:
                symbols.sort()

            logger.debug(f"Processed {len(vector_data)} vectors into {len(symbols)} symbols")
            return symbols

        except Exception as e:
            raise ObservationError(
                f"Failed to process vectors: {str(e)}",
                observation_data={"vector_count": len(vector_data)}
            )

    def process_strings(self, string_data: list[str]) -> list[str]:
        """
        Process string symbols.

        Args:
            string_data: List of string symbols

        Returns:
            Processed list of string symbols (possibly sorted)
        """
        if not string_data:
            return []

        # Copy to avoid modifying original
        symbols = string_data[:]

        # Sort if configured
        if symbols and self.sort_symbols:
            symbols.sort()

        logger.debug(f"Processed {len(string_data)} string symbols")
        return symbols

    def process_emotives(self, emotives_data: dict[str, float]) -> None:
        """
        Process emotional/utility values.

        NOTE: This method is deprecated. Emotives processing now happens in KatoProcessor.observe()
        using MemoryManager.process_emotives() static method. Kept for backward compatibility.

        Args:
            emotives_data: Dictionary of emotive values
        """
        if emotives_data:
            logger.debug(f"Processed {len(emotives_data)} emotive dimensions")

    def process_metadata(self, metadata_data: dict[str, Any]) -> None:
        """
        Process pattern metadata.

        NOTE: This method is deprecated. Metadata processing now happens in KatoProcessor.observe()
        using MemoryManager.process_metadata() static method. Kept for backward compatibility.

        Args:
            metadata_data: Dictionary of metadata values
        """
        if metadata_data:
            logger.debug(f"Processed {len(metadata_data)} metadata keys")

    def check_auto_learning(
        self,
        stm: list[list[str]],
        emotives: list[dict[str, float]],
        metadata: list[dict[str, Any]],
        max_pattern_length: int,
        stm_mode: str,
    ) -> tuple[Optional[str], list[list[str]]]:
        """
        Auto-learn from the given STM if it has reached max_pattern_length.

        Supports two modes:
        - CLEAR mode: learn the pattern and return an empty STM (original behavior)
        - ROLLING mode: learn the pattern and return the last N-1 events as the
          new STM, so the window keeps sliding

        Stateless: operates on the STM it is given and returns the STM to keep.

        Args:
            stm: Current STM (events, oldest first)
            emotives: Emotives to store with an auto-learned pattern
            metadata: Metadata to store with an auto-learned pattern
            max_pattern_length: Maximum pattern length for auto-learning (0 = disabled)
            stm_mode: STM mode ('CLEAR' or 'ROLLING')

        Returns:
            (pattern name or None, STM after auto-learning)
        """
        logger.debug(f"check_auto_learning: max_pattern_length={max_pattern_length}")
        if max_pattern_length <= 0:
            logger.debug(f"Auto-learning disabled (max_pattern_length={max_pattern_length})")
            return None, stm

        stm_length = len(stm)

        # Normalize invalid modes to CLEAR
        if stm_mode not in ['CLEAR', 'ROLLING']:
            stm_mode = 'CLEAR'
        logger.info(f"check_auto_learning: STM length={stm_length}, max={max_pattern_length}, mode={stm_mode}")

        if stm_length < max_pattern_length:
            return None, stm

        logger.info(f"Auto-learning triggered: STM length {stm_length} >= "
                    f"max_pattern_length {max_pattern_length} (mode: {stm_mode})")

        # A single-event STM is "learned" for compatibility: nothing is stored
        # (patterns need two events) but the STM is cleared, as it always was.
        pattern_name = self.pattern_operations.learn_pattern_from(stm, emotives, metadata) or None

        if stm_mode == 'ROLLING' and stm_length > 1:
            # ROLLING mode: keep the last N-1 events as the new window
            window_size = max_pattern_length - 1
            new_stm = stm[-window_size:] if len(stm) > window_size else stm[1:]
            logger.info(f"ROLLING mode: keeping {len(new_stm)} events as the new window")
            return pattern_name, list(new_stm)

        return pattern_name, []

    async def process_observation(
        self,
        data: dict[str, Any],
        config=None,
        *,
        stm: list[list[str]],
        emotives: Optional[list[dict[str, float]]] = None,
        metadata: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Process a complete observation including strings, vectors, and emotives.

        This is the main entry point for processing observations. It:
        1. Validates the input data
        2. Processes vectors to get symbolic representations
        3. Processes string symbols
        4. Processes emotives
        5. Updates STM with combined symbols
        6. Triggers predictions
        7. Checks for auto-learning

        Args:
            data: Observation data containing:
                - unique_id: Unique identifier for the observation
                - strings: List of string symbols
                - vectors: List of vector embeddings
                - emotives: Dictionary of emotional values
                - path: Processing path (optional)
                - metadata: Additional metadata (optional)
            config: Optional SessionConfiguration for session-specific behavior

        Returns:
            Dictionary containing:
                - unique_id: The observation's unique ID
                - auto_learned_pattern: Pattern name if auto-learning occurred
                - symbols: Combined list of processed symbols
                - predictions: Generated predictions (if any)

        Raises:
            ObservationError: If observation processing fails
            ValidationError: If input validation fails
        """
        # Per-request state: the STM is the caller's (session) STM; this method
        # never touches the shared pattern_processor's own STM, so concurrent
        # requests on one processor cannot see each other's events and no lock
        # is needed.
        working_stm: list[list[str]] = [list(event) for event in stm]
        learn_emotives = list(emotives) if emotives else []
        learn_metadata = list(metadata) if metadata else []
        try:
            # Validate input
            self.validate_observation(data)

            # Extract config values (use provided config or fallback to instance defaults)
            max_pattern_length = config.max_pattern_length if config and config.max_pattern_length is not None else self.max_pattern_length
            process_predictions = config.process_predictions if config and config.process_predictions is not None else self.process_predictions
            stm_mode = config.stm_mode if config and config.stm_mode is not None else getattr(self.pattern_processor, 'stm_mode', 'CLEAR')
            sort_symbols = config.sort_symbols if config and config.sort_symbols is not None else self.sort_symbols

            unique_id = data['unique_id']
            string_data = data.get('strings', [])
            vector_data = data.get('vectors', [])
            emotives_data = data.get('emotives', {})
            metadata_data = data.get('metadata', {})

            # Add processing path
            if 'path' not in data:
                data['path'] = []
            # Get processor info from pattern processor's genome manifest
            processor_name = getattr(self.pattern_processor, 'name', 'kato')
            processor_id = getattr(self.pattern_processor, 'id', 'unknown')
            data['path'] += [f'{processor_name}-{processor_id}-process']

            # NOTE: percept_data, time, emotives, metadata are now handled in KatoProcessor.observe()
            # This processor only handles symbolic processing and predictions

            # Process different data types
            v_identified = self.process_vectors(vector_data) if vector_data else []
            symbols = self.process_strings(string_data) if string_data else []

            if emotives_data:
                self.process_emotives(emotives_data)  # Deprecated, just logs

            if metadata_data:
                self.process_metadata(metadata_data)  # Deprecated, just logs

            # Combine all symbols
            combined_symbols = v_identified + symbols

            # Only trigger predictions if we have actual symbolic content
            predictions = []
            if vector_data or string_data:
                # Only trigger predictions if enabled
                # Add current symbols to STM
                if combined_symbols:
                    working_stm.append(list(combined_symbols))

                # Generate predictions ONLY if enabled
                if process_predictions:
                    predictions = await self.pattern_processor.predict_from(
                        working_stm, unique_id, trigger_predictions=process_predictions
                    )
                    logger.debug(f"Generated {len(predictions)} predictions (process_predictions=True)")
                else:
                    logger.debug("Skipping prediction computation (process_predictions=False)")

                # Check for auto-learning AFTER adding current event
                # Pass config values to check_auto_learning
                logger.debug(f"About to check auto-learning with max_pattern_length={max_pattern_length}")
                auto_learned_pattern, working_stm = self.check_auto_learning(
                    working_stm,
                    learn_emotives,
                    learn_metadata,
                    max_pattern_length=max_pattern_length,
                    stm_mode=stm_mode,
                )
                logger.debug(f"Auto-learning result: {auto_learned_pattern}")
            else:
                logger.debug("No data to process, skipping auto-learning check")
                auto_learned_pattern = None

            return {
                'unique_id': unique_id,
                'auto_learned_pattern': auto_learned_pattern,
                'symbols': combined_symbols,
                'predictions': predictions,
                'stm': working_stm,
            }

        except (ValidationError, ObservationError):
            # Re-raise known exceptions
            raise
        except Exception as e:
            # Wrap unknown exceptions
            raise ObservationError(
                f"Failed to process observation: {str(e)}",
                observation_id=data.get('unique_id'),
                observation_data=data
            )
