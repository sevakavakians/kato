"""
Observation Processor for KATO
Handles processing of incoming observations including strings, vectors, and emotives.
Extracted from KatoProcessor for better modularity.
"""

import logging
from multiprocessing import Lock
from typing import Any, Dict, List, Optional

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
                 pattern_operations, sort_symbols, max_pattern_length):
        """
        Initialize observation processor with references to other components.
        
        Args:
            vector_processor: Reference to vector processor for vector operations
            pattern_processor: Reference to pattern processor for STM operations
            memory_manager: Reference to memory manager for state management
            pattern_operations: Reference to pattern operations for learning
            sort_symbols: Whether to sort symbols alphabetically
            max_pattern_length: Maximum pattern length for auto-learning
        """
        self.vector_processor = vector_processor
        self.pattern_processor = pattern_processor
        self.memory_manager = memory_manager
        self.pattern_operations = pattern_operations

        # Get configuration passed in
        self.sort_symbols = sort_symbols
        self.max_pattern_length = max_pattern_length

        # Processing lock for thread safety
        self.processing_lock = Lock()

        logger.debug("ObservationProcessor initialized")

    def validate_observation(self, data: Dict[str, Any]) -> None:
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

    def process_vectors(self, vector_data: List[List[float]]) -> List[str]:
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

    def process_strings(self, string_data: List[str]) -> List[str]:
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

    def process_emotives(self, emotives_data: Dict[str, float]) -> None:
        """
        Process emotional/utility values.
        
        Args:
            emotives_data: Dictionary of emotive values
        """
        if emotives_data:
            self.memory_manager.process_emotives(emotives_data)
            logger.debug(f"Processed {len(emotives_data)} emotive dimensions")

    def check_auto_learning(self) -> Optional[str]:
        """
        Check if auto-learning should be triggered and perform it if needed.
        
        Supports two modes:
        - CLEAR mode: Learn pattern and completely clear STM (original behavior)
        - ROLLING mode: Learn pattern and maintain STM as a rolling window
        
        Returns:
            Pattern name if auto-learning occurred, None otherwise
        """
        logger.debug(f"check_auto_learning: max_pattern_length={self.max_pattern_length}")
        if self.max_pattern_length <= 0:
            logger.debug(f"Auto-learning disabled (max_pattern_length={self.max_pattern_length})")
            return None

        stm_length = self.memory_manager.get_stm_length()
        stm_mode = getattr(self.pattern_processor, 'stm_mode', 'CLEAR')
        # Normalize invalid modes to CLEAR
        if stm_mode not in ['CLEAR', 'ROLLING']:
            stm_mode = 'CLEAR'
        logger.info(f"check_auto_learning: STM length={stm_length}, max={self.max_pattern_length}, mode={stm_mode}")

        if stm_length >= self.max_pattern_length:
            logger.info(f"Auto-learning triggered: STM length {stm_length} >= "
                       f"max_pattern_length {self.max_pattern_length} (mode: {stm_mode})")

            if stm_length > 1:
                if stm_mode == 'ROLLING':
                    # ROLLING mode: Save the last N-1 events before learning
                    stm_state = self.memory_manager.get_stm_state()
                    window_size = self.max_pattern_length - 1
                    events_to_restore = stm_state[-window_size:] if len(stm_state) > window_size else stm_state[1:]

                    # Learn pattern (this clears STM)
                    pattern_name = self.pattern_operations.learn_pattern(keep_stm_for_rolling=True)

                    # Restore the rolling window events
                    if events_to_restore:
                        self.pattern_processor.setSTM(events_to_restore)
                        logger.debug(f"Restored rolling window events: {events_to_restore}")

                    if pattern_name:
                        logger.info(f"Auto-learned pattern in ROLLING mode: {pattern_name}")
                        return pattern_name
                else:
                    # CLEAR mode: Learn pattern and clear STM completely (original behavior)
                    pattern_name = self.pattern_operations.learn_pattern(keep_tail=False)

                    if pattern_name:
                        logger.info(f"Auto-learned pattern in CLEAR mode: {pattern_name}")
                        return pattern_name

            elif stm_length == 1:
                # Only one event: learn it regardless of mode
                pattern_name = self.pattern_operations.learn_pattern(keep_tail=False)
                if pattern_name:
                    logger.info(f"Auto-learned single-event pattern: {pattern_name}")
                    return pattern_name

        return None

    async def process_observation(self, data: Dict[str, Any]) -> Dict[str, Any]:
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
        with self.processing_lock:
            try:
                # Validate input
                self.validate_observation(data)

                unique_id = data['unique_id']
                string_data = data.get('strings', [])
                vector_data = data.get('vectors', [])
                emotives_data = data.get('emotives', {})

                # Add processing path
                if 'path' not in data:
                    data['path'] = []
                # Get processor info from pattern processor's genome manifest
                processor_name = getattr(self.pattern_processor, 'name', 'kato')
                processor_id = getattr(self.pattern_processor, 'id', 'unknown')
                data['path'] += [f'{processor_name}-{processor_id}-process']

                # Update percept data in memory manager
                self.memory_manager.update_percept_data(
                    string_data,
                    vector_data,
                    emotives_data,
                    data['path'],
                    data.get('metadata', {})
                )

                # Increment time counter
                self.memory_manager.increment_time()

                # Process different data types
                v_identified = self.process_vectors(vector_data) if vector_data else []
                symbols = self.process_strings(string_data) if string_data else []

                if emotives_data:
                    self.process_emotives(emotives_data)

                # Combine all symbols
                combined_symbols = v_identified + symbols
                self.memory_manager.symbols = combined_symbols

                # Only trigger predictions if we have actual symbolic content
                predictions = []
                if vector_data or string_data:
                    self.pattern_processor.trigger_predictions = True

                    # Add current symbols to STM
                    self.pattern_processor.setCurrentEvent(combined_symbols)

                    # Generate predictions
                    predictions = await self.pattern_processor.processEvents(unique_id)

                    # Check for auto-learning AFTER adding current event
                    # This matches the original behavior where auto-learning happens
                    # when STM reaches the max length AFTER the new observation
                    logger.debug(f"About to check auto-learning with max_pattern_length={self.max_pattern_length}")
                    auto_learned_pattern = self.check_auto_learning()
                    logger.debug(f"Auto-learning result: {auto_learned_pattern}")
                else:
                    logger.debug("No data to process, skipping auto-learning check")
                    auto_learned_pattern = None

                return {
                    'unique_id': unique_id,
                    'auto_learned_pattern': auto_learned_pattern,
                    'symbols': combined_symbols,
                    'predictions': predictions
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
