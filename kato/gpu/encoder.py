"""
Symbol Vocabulary Encoder for GPU Pattern Matching.

Converts string symbols to integer IDs for efficient GPU processing.
Maintains bidirectional mapping with MongoDB persistence.

Usage:
    >>> from kato.gpu.encoder import SymbolVocabularyEncoder
    >>> encoder = SymbolVocabularyEncoder(mongodb.metadata)
    >>>
    >>> # Encode symbols
    >>> encoded = encoder.encode_sequence(['hello', 'world'])
    >>> # Returns: np.array([0, 1], dtype=np.int32)
    >>>
    >>> # Decode symbols
    >>> decoded = encoder.decode_sequence(encoded)
    >>> # Returns: ['hello', 'world']

Design:
    - Bidirectional mapping: string ↔ integer ID
    - MongoDB persistence for vocabulary
    - Thread-safe operations (MongoDB atomic updates)
    - Padding value: -1 (filtered in decoding)
    - Deterministic ordering: alphabetical symbol sorting
"""

import logging
from typing import Dict, List, Optional

import numpy as np
from pymongo.collection import Collection

logger = logging.getLogger('kato.gpu.encoder')


class SymbolVocabularyEncoder:
    """
    Bidirectional mapping between string symbols and integer IDs.

    The encoder maintains a vocabulary of symbols seen during pattern learning
    and provides fast conversion between string and integer representations.

    Attributes:
        symbol_to_id: Dict mapping symbols to integer IDs
        id_to_symbol: Dict mapping integer IDs to symbols
        vocab_size: Number of unique symbols in vocabulary
        next_id: Next available ID for new symbols
        mongodb: MongoDB metadata collection for persistence

    Thread Safety:
        MongoDB operations are atomic, providing thread-safe vocabulary updates.
        In-memory caches are rebuilt on load for consistency.
    """

    def __init__(self, mongodb_metadata: Collection):
        """
        Initialize encoder with MongoDB backend.

        Args:
            mongodb_metadata: MongoDB metadata collection for persistence
        """
        self.mongodb = mongodb_metadata
        self.symbol_to_id: Dict[str, int] = {}
        self.id_to_symbol: Dict[int, str] = {}
        self.next_id: int = 0

        # Load existing vocabulary from MongoDB
        self._load_vocabulary()

        logger.info(f"SymbolVocabularyEncoder initialized with {self.vocab_size} symbols")

    @property
    def vocab_size(self) -> int:
        """Get current vocabulary size."""
        return len(self.symbol_to_id)

    def _load_vocabulary(self):
        """Load vocabulary from MongoDB."""
        vocab_doc = self.mongodb.find_one({"class": "gpu_vocabulary"})

        if vocab_doc:
            # Load existing vocabulary
            self.symbol_to_id = vocab_doc['symbol_to_id']
            # MongoDB stores dict keys as strings, convert back to int
            self.id_to_symbol = {int(k): v for k, v in vocab_doc['id_to_symbol'].items()}
            self.next_id = vocab_doc['next_id']
            logger.info(f"Loaded vocabulary: {self.vocab_size} symbols")
        else:
            # Initialize empty vocabulary
            logger.info("No existing vocabulary found, starting fresh")

    def _save_vocabulary(self):
        """Persist vocabulary to MongoDB."""
        self.mongodb.update_one(
            {"class": "gpu_vocabulary"},
            {
                "$set": {
                    "symbol_to_id": self.symbol_to_id,
                    # Convert int keys to strings for MongoDB compatibility
                    "id_to_symbol": {str(k): v for k, v in self.id_to_symbol.items()},
                    "vocab_size": self.vocab_size,
                    "next_id": self.next_id
                }
            },
            upsert=True
        )

    def encode_symbol(self, symbol: str) -> int:
        """
        Encode a single symbol to integer ID.

        If the symbol hasn't been seen before, assigns it a new ID and
        persists the vocabulary to MongoDB.

        Args:
            symbol: String symbol to encode

        Returns:
            Integer ID for the symbol

        Example:
            >>> encoder.encode_symbol('hello')
            0
            >>> encoder.encode_symbol('world')
            1
            >>> encoder.encode_symbol('hello')  # Same ID for same symbol
            0
        """
        if symbol not in self.symbol_to_id:
            # Add new symbol
            self.symbol_to_id[symbol] = self.next_id
            self.id_to_symbol[self.next_id] = symbol
            self.next_id += 1

            # Persist to MongoDB
            # TODO: For performance, batch these writes when encoding many symbols
            self._save_vocabulary()

            logger.debug(f"Added new symbol: '{symbol}' -> {self.next_id - 1}")

        return self.symbol_to_id[symbol]

    def decode_symbol(self, symbol_id: int) -> Optional[str]:
        """
        Decode integer ID back to symbol.

        Args:
            symbol_id: Integer ID to decode

        Returns:
            String symbol, or None if ID not found

        Example:
            >>> encoder.decode_symbol(0)
            'hello'
            >>> encoder.decode_symbol(999)
            None
        """
        return self.id_to_symbol.get(symbol_id)

    def encode_sequence(self, sequence: List[str]) -> np.ndarray:
        """
        Encode a sequence of symbols to integer array.

        Args:
            sequence: List of string symbols

        Returns:
            NumPy array of integer IDs (dtype=int32)

        Example:
            >>> encoder.encode_sequence(['hello', 'world'])
            array([0, 1], dtype=int32)
        """
        encoded = [self.encode_symbol(s) for s in sequence]
        return np.array(encoded, dtype=np.int32)

    def decode_sequence(self, encoded: np.ndarray) -> List[str]:
        """
        Decode integer array back to symbols.

        Filters out padding values (-1) during decoding.

        Args:
            encoded: NumPy array of integer IDs

        Returns:
            List of string symbols (padding removed)

        Example:
            >>> encoded = np.array([0, 1, -1, -1], dtype=np.int32)
            >>> encoder.decode_sequence(encoded)
            ['hello', 'world']
        """
        symbols = []
        for symbol_id in encoded:
            if symbol_id >= 0:  # Skip padding (-1)
                symbol = self.decode_symbol(int(symbol_id))
                if symbol:
                    symbols.append(symbol)
        return symbols

    def encode_pattern(self, pattern_data: List[List[str]]) -> List[np.ndarray]:
        """
        Encode a pattern (list of events) to list of integer arrays.

        Args:
            pattern_data: Pattern as list of events (each event is list of symbols)

        Returns:
            List of NumPy arrays, one per event

        Example:
            >>> pattern = [['hello', 'world'], ['foo', 'bar']]
            >>> encoded_pattern = encoder.encode_pattern(pattern)
            >>> len(encoded_pattern)
            2
            >>> encoded_pattern[0]
            array([0, 1], dtype=int32)
        """
        return [self.encode_sequence(event) for event in pattern_data]

    def decode_pattern(self, encoded_pattern: List[np.ndarray]) -> List[List[str]]:
        """
        Decode a pattern from list of integer arrays to list of events.

        Args:
            encoded_pattern: List of NumPy arrays (one per event)

        Returns:
            Pattern as list of events (each event is list of symbols)

        Example:
            >>> encoded = [np.array([0, 1]), np.array([2, 3])]
            >>> encoder.decode_pattern(encoded)
            [['hello', 'world'], ['foo', 'bar']]
        """
        return [self.decode_sequence(event) for event in encoded_pattern]

    def build_from_patterns(self, patterns_collection: Collection, batch_size: int = 1000):
        """
        Build vocabulary from existing patterns in MongoDB.

        Scans all patterns and creates mappings for all unique symbols.
        Uses deterministic ordering (alphabetically sorted) for reproducibility.

        Args:
            patterns_collection: MongoDB patterns_kb collection
            batch_size: Number of patterns to process per batch (for memory efficiency)

        Example:
            >>> encoder.build_from_patterns(kb.patterns_kb)
            >>> print(f"Built vocabulary with {encoder.vocab_size} symbols")
        """
        logger.info("Building vocabulary from patterns...")

        # Use aggregation pipeline to get unique symbols efficiently
        # MongoDB aggregation is much faster than loading all patterns into memory
        pipeline = [
            {"$project": {"pattern_data": 1}},      # Only get pattern_data field
            {"$unwind": "$pattern_data"},           # Flatten events
            {"$unwind": "$pattern_data"},           # Flatten symbols
            {"$group": {"_id": "$pattern_data"}},   # Get unique symbols
            {"$sort": {"_id": 1}}                   # Alphabetical order (deterministic)
        ]

        unique_symbols = patterns_collection.aggregate(pipeline)

        # Assign IDs in alphabetical order (deterministic)
        count = 0
        for doc in unique_symbols:
            symbol = doc['_id']
            if symbol not in self.symbol_to_id:
                self.symbol_to_id[symbol] = self.next_id
                self.id_to_symbol[self.next_id] = symbol
                self.next_id += 1
                count += 1

        # Save to MongoDB
        self._save_vocabulary()

        logger.info(f"Built vocabulary: {self.vocab_size} unique symbols ({count} new)")

    def clear(self):
        """
        Clear vocabulary and reset to empty state.

        Removes all symbol mappings and persists empty vocabulary to MongoDB.

        Example:
            >>> encoder.clear()
            >>> encoder.vocab_size
            0
        """
        self.symbol_to_id.clear()
        self.id_to_symbol.clear()
        self.next_id = 0
        self._save_vocabulary()
        logger.info("Vocabulary cleared")

    def get_stats(self) -> Dict[str, any]:
        """
        Get statistics about the vocabulary.

        Returns:
            Dictionary with vocabulary statistics

        Example:
            >>> stats = encoder.get_stats()
            >>> print(stats)
            {
                'vocab_size': 150,
                'next_id': 150,
                'memory_usage_bytes': 12000
            }
        """
        import sys

        return {
            'vocab_size': self.vocab_size,
            'next_id': self.next_id,
            'memory_usage_bytes': (
                sys.getsizeof(self.symbol_to_id) +
                sys.getsizeof(self.id_to_symbol)
            )
        }

    def __repr__(self) -> str:
        """String representation of encoder."""
        return f"SymbolVocabularyEncoder(vocab_size={self.vocab_size})"
