"""
Unit tests for SymbolVocabularyEncoder.

Tests cover:
- Basic encoding/decoding operations
- Persistence and reloading
- Edge cases (empty sequences, padding, special characters)
- Large vocabularies
- Pattern encoding/decoding
"""

import pytest
import numpy as np

from kato.gpu.encoder import SymbolVocabularyEncoder
from tests.gpu.data_generators import (
    generate_test_symbols,
    generate_random_patterns,
    flatten_pattern
)


class TestBasicEncoding:
    """Test basic encoding and decoding operations."""

    def test_encode_single_symbol(self, encoder):
        """Test encoding a single symbol."""
        symbol_id = encoder.encode_symbol("test_symbol")

        assert isinstance(symbol_id, int)
        assert symbol_id >= 0
        assert encoder.vocab_size == 1

    def test_encode_decode_roundtrip(self, encoder):
        """Test encoding and decoding preserve symbol."""
        original = "test_symbol"

        symbol_id = encoder.encode_symbol(original)
        decoded = encoder.decode_symbol(symbol_id)

        assert decoded == original

    def test_consistent_encoding(self, encoder):
        """Test same symbol always gets same ID."""
        id1 = encoder.encode_symbol("test")
        id2 = encoder.encode_symbol("test")
        id3 = encoder.encode_symbol("test")

        assert id1 == id2 == id3

    def test_different_symbols_different_ids(self, encoder):
        """Test different symbols get different IDs."""
        id1 = encoder.encode_symbol("symbol1")
        id2 = encoder.encode_symbol("symbol2")
        id3 = encoder.encode_symbol("symbol3")

        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    def test_sequential_ids(self, encoder):
        """Test IDs are assigned sequentially."""
        ids = []
        for i in range(10):
            symbol_id = encoder.encode_symbol(f"sym{i}")
            ids.append(symbol_id)

        # IDs should be 0, 1, 2, ..., 9
        assert ids == list(range(10))


class TestSequenceEncoding:
    """Test sequence encoding and decoding."""

    def test_encode_sequence(self, encoder):
        """Test encoding a sequence of symbols."""
        sequence = ["a", "b", "c", "d"]
        encoded = encoder.encode_sequence(sequence)

        assert isinstance(encoded, np.ndarray)
        assert encoded.dtype == np.int32
        assert len(encoded) == len(sequence)
        assert all(encoded >= 0)

    def test_decode_sequence(self, encoder):
        """Test decoding a sequence."""
        original = ["a", "b", "c", "d"]

        encoded = encoder.encode_sequence(original)
        decoded = encoder.decode_sequence(encoded)

        assert decoded == original

    def test_sequence_order_preserved(self, encoder):
        """Test sequence order is preserved."""
        sequence = ["z", "a", "m", "b"]  # Not alphabetical
        encoded = encoder.encode_sequence(sequence)
        decoded = encoder.decode_sequence(encoded)

        assert decoded == sequence  # Order preserved

    def test_empty_sequence(self, encoder):
        """Test encoding empty sequence."""
        encoded = encoder.encode_sequence([])

        assert len(encoded) == 0
        assert encoded.dtype == np.int32

    def test_empty_sequence_decode(self, encoder):
        """Test decoding empty sequence."""
        decoded = encoder.decode_sequence(np.array([], dtype=np.int32))

        assert decoded == []


class TestPadding:
    """Test padding handling."""

    def test_padding_filtered_in_decode(self, encoder):
        """Test that padding (-1) is filtered in decoding."""
        sequence = ["a", "b", "c"]
        encoded = encoder.encode_sequence(sequence)

        # Add padding
        padded = np.pad(encoded, (0, 5), constant_values=-1)
        assert padded[-1] == -1  # Verify padding added

        # Decode should filter padding
        decoded = encoder.decode_sequence(padded)

        assert decoded == sequence

    def test_padding_at_beginning(self, encoder):
        """Test padding at beginning is filtered."""
        sequence = ["a", "b"]
        encoded = encoder.encode_sequence(sequence)

        # Add padding at beginning
        padded = np.concatenate([np.array([-1, -1], dtype=np.int32), encoded])

        decoded = encoder.decode_sequence(padded)

        assert decoded == sequence

    def test_padding_in_middle(self, encoder):
        """Test padding in middle is filtered."""
        seq1 = ["a", "b"]
        seq2 = ["c", "d"]

        enc1 = encoder.encode_sequence(seq1)
        enc2 = encoder.encode_sequence(seq2)

        # Insert padding in middle
        padded = np.concatenate([
            enc1,
            np.array([-1, -1, -1], dtype=np.int32),
            enc2
        ])

        decoded = encoder.decode_sequence(padded)

        # Should get seq1 + seq2 without padding
        assert decoded == seq1 + seq2


class TestPersistence:
    """Test MongoDB persistence."""

    def test_persistence_across_instances(self, mongodb):
        """Test vocabulary persists to MongoDB."""
        # Create encoder and add symbols
        encoder1 = SymbolVocabularyEncoder(mongodb.metadata)
        encoder1.encode_symbol("symbol1")
        encoder1.encode_symbol("symbol2")
        encoder1.encode_symbol("symbol3")

        # Create new encoder (should load saved vocab)
        encoder2 = SymbolVocabularyEncoder(mongodb.metadata)

        assert encoder2.vocab_size == 3
        assert encoder2.encode_symbol("symbol1") == encoder1.encode_symbol("symbol1")
        assert encoder2.encode_symbol("symbol2") == encoder1.encode_symbol("symbol2")
        assert encoder2.encode_symbol("symbol3") == encoder1.encode_symbol("symbol3")

    def test_new_symbols_persist(self, mongodb):
        """Test new symbols are persisted."""
        encoder1 = SymbolVocabularyEncoder(mongodb.metadata)
        encoder1.encode_symbol("initial")

        encoder2 = SymbolVocabularyEncoder(mongodb.metadata)
        encoder2.encode_symbol("new_symbol")

        encoder3 = SymbolVocabularyEncoder(mongodb.metadata)
        assert encoder3.vocab_size == 2
        assert "initial" in encoder3.symbol_to_id
        assert "new_symbol" in encoder3.symbol_to_id


class TestLargeVocabulary:
    """Test with large vocabularies."""

    def test_large_vocabulary(self, encoder):
        """Test with large vocabulary."""
        symbols = generate_test_symbols(1000)

        # Encode all
        for symbol in symbols:
            encoder.encode_symbol(symbol)

        assert encoder.vocab_size == 1000

        # Verify all encodings unique
        ids = [encoder.encode_symbol(s) for s in symbols]
        assert len(set(ids)) == 1000

    def test_large_vocabulary_decoding(self, encoder):
        """Test decoding with large vocabulary."""
        symbols = generate_test_symbols(500)

        # Encode all
        encoded = encoder.encode_sequence(symbols)

        # Decode all
        decoded = encoder.decode_sequence(encoded)

        assert decoded == symbols


class TestSpecialCharacters:
    """Test encoding symbols with special characters."""

    def test_pipe_character(self, encoder):
        """Test symbols with pipe character."""
        symbols = ["hello|world", "VCTR|abc123"]

        for symbol in symbols:
            symbol_id = encoder.encode_symbol(symbol)
            decoded = encoder.decode_symbol(symbol_id)
            assert decoded == symbol

    def test_underscore(self, encoder):
        """Test symbols with underscore."""
        symbol = "sym_with_underscore"
        symbol_id = encoder.encode_symbol(symbol)
        decoded = encoder.decode_symbol(symbol_id)
        assert decoded == symbol

    def test_dash(self, encoder):
        """Test symbols with dash."""
        symbol = "sym-with-dash"
        symbol_id = encoder.encode_symbol(symbol)
        decoded = encoder.decode_symbol(symbol_id)
        assert decoded == symbol

    def test_dots(self, encoder):
        """Test symbols with dots."""
        symbol = "sym.with.dots"
        symbol_id = encoder.encode_symbol(symbol)
        decoded = encoder.decode_symbol(symbol_id)
        assert decoded == symbol

    def test_numbers(self, encoder):
        """Test symbols with numbers."""
        symbols = ["sym123", "test456", "v1.2.3"]

        for symbol in symbols:
            symbol_id = encoder.encode_symbol(symbol)
            decoded = encoder.decode_symbol(symbol_id)
            assert decoded == symbol


class TestPatternEncoding:
    """Test encoding and decoding patterns (list of events)."""

    def test_encode_pattern(self, encoder):
        """Test encoding a pattern."""
        pattern = [['a', 'b'], ['c', 'd'], ['e', 'f']]

        encoded_pattern = encoder.encode_pattern(pattern)

        assert len(encoded_pattern) == 3
        assert all(isinstance(event, np.ndarray) for event in encoded_pattern)
        assert all(event.dtype == np.int32 for event in encoded_pattern)

    def test_decode_pattern(self, encoder):
        """Test decoding a pattern."""
        original_pattern = [['a', 'b'], ['c', 'd'], ['e', 'f']]

        encoded_pattern = encoder.encode_pattern(original_pattern)
        decoded_pattern = encoder.decode_pattern(encoded_pattern)

        assert decoded_pattern == original_pattern

    def test_pattern_with_random_data(self, encoder):
        """Test pattern encoding with random data."""
        patterns = generate_random_patterns(5, seed=42)

        for pattern in patterns:
            encoded = encoder.encode_pattern(pattern)
            decoded = encoder.decode_pattern(encoded)
            assert decoded == pattern


class TestClear:
    """Test vocabulary clearing."""

    def test_clear(self, encoder):
        """Test clearing vocabulary."""
        encoder.encode_symbol("test1")
        encoder.encode_symbol("test2")
        encoder.encode_symbol("test3")

        assert encoder.vocab_size == 3

        encoder.clear()

        assert encoder.vocab_size == 0
        assert len(encoder.symbol_to_id) == 0
        assert len(encoder.id_to_symbol) == 0
        assert encoder.next_id == 0

    def test_clear_persists(self, mongodb):
        """Test that clear persists to MongoDB."""
        encoder1 = SymbolVocabularyEncoder(mongodb.metadata)
        encoder1.encode_symbol("test1")
        encoder1.encode_symbol("test2")

        encoder1.clear()

        encoder2 = SymbolVocabularyEncoder(mongodb.metadata)
        assert encoder2.vocab_size == 0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_decode_unknown_id(self, encoder):
        """Test decoding unknown ID returns None."""
        result = encoder.decode_symbol(999)
        assert result is None

    def test_decode_sequence_with_unknown_ids(self, encoder):
        """Test decoding sequence filters unknown IDs."""
        # Encode some valid symbols
        encoder.encode_symbol("a")
        encoder.encode_symbol("b")

        # Create array with valid and invalid IDs
        mixed = np.array([0, 1, 999, 1000], dtype=np.int32)

        decoded = encoder.decode_sequence(mixed)

        # Should only decode valid IDs
        assert decoded == ["a", "b"]

    def test_get_stats(self, encoder):
        """Test getting vocabulary statistics."""
        encoder.encode_symbol("test1")
        encoder.encode_symbol("test2")

        stats = encoder.get_stats()

        assert stats['vocab_size'] == 2
        assert stats['next_id'] == 2
        assert 'memory_usage_bytes' in stats

    def test_repr(self, encoder):
        """Test string representation."""
        encoder.encode_symbol("test")

        repr_str = repr(encoder)

        assert "SymbolVocabularyEncoder" in repr_str
        assert "vocab_size=1" in repr_str


class TestBuildFromPatterns:
    """Test building vocabulary from existing patterns."""

    def test_build_from_empty_collection(self, encoder, mongodb):
        """Test building from empty pattern collection."""
        patterns_collection = mongodb.patterns_kb

        encoder.build_from_patterns(patterns_collection)

        assert encoder.vocab_size == 0

    def test_build_from_patterns(self, encoder, mongodb):
        """Test building vocabulary from patterns."""
        patterns_collection = mongodb.patterns_kb

        # Insert test patterns
        patterns_collection.insert_many([
            {"name": "P1", "pattern_data": [["a", "b"], ["c", "d"]]},
            {"name": "P2", "pattern_data": [["e", "f"], ["g", "h"]]},
            {"name": "P3", "pattern_data": [["a", "e"]]}  # Some overlap
        ])

        encoder.build_from_patterns(patterns_collection)

        # Should have 8 unique symbols: a, b, c, d, e, f, g, h
        assert encoder.vocab_size == 8

        # Verify all symbols present
        expected_symbols = ["a", "b", "c", "d", "e", "f", "g", "h"]
        for symbol in expected_symbols:
            assert symbol in encoder.symbol_to_id

    def test_build_alphabetical_order(self, encoder, mongodb):
        """Test that build uses alphabetical ordering."""
        patterns_collection = mongodb.patterns_kb

        # Insert pattern with non-alphabetical symbols
        patterns_collection.insert_one({
            "name": "P1",
            "pattern_data": [["z", "a", "m", "b"]]
        })

        encoder.build_from_patterns(patterns_collection)

        # IDs should be assigned alphabetically
        assert encoder.encode_symbol("a") < encoder.encode_symbol("b")
        assert encoder.encode_symbol("b") < encoder.encode_symbol("m")
        assert encoder.encode_symbol("m") < encoder.encode_symbol("z")
