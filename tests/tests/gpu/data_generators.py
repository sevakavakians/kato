"""
Test data generators for GPU tests.

Provides utilities for generating random patterns, symbols, and sequences
for testing GPU components.
"""

import numpy as np
from itertools import chain
from typing import List, Tuple


def generate_random_patterns(
    count: int,
    min_events: int = 2,
    max_events: int = 5,
    min_symbols_per_event: int = 3,
    max_symbols_per_event: int = 10,
    seed: int = None
) -> List[List[List[str]]]:
    """
    Generate random patterns for testing.

    Args:
        count: Number of patterns to generate
        min_events: Minimum number of events per pattern
        max_events: Maximum number of events per pattern
        min_symbols_per_event: Minimum symbols per event
        max_symbols_per_event: Maximum symbols per event
        seed: Random seed for reproducibility (optional)

    Returns:
        List of patterns, where each pattern is a list of events,
        and each event is a list of symbols.

    Example:
        >>> patterns = generate_random_patterns(10, seed=42)
        >>> len(patterns)
        10
        >>> all(isinstance(p, list) for p in patterns)
        True
    """
    if seed is not None:
        np.random.seed(seed)

    # Vocabulary of test symbols
    vocab = [f"sym{i}" for i in range(100)]
    vocab += [f"VCTR|{i:04x}" for i in range(50)]

    patterns = []
    for _ in range(count):
        num_events = np.random.randint(min_events, max_events + 1)
        pattern = []

        for _ in range(num_events):
            num_symbols = np.random.randint(min_symbols_per_event, max_symbols_per_event + 1)
            event = sorted(list(np.random.choice(vocab, num_symbols, replace=False)))
            pattern.append(event)

        patterns.append(pattern)

    return patterns


def generate_test_symbols(count: int = 100, include_vectors: bool = True) -> List[str]:
    """
    Generate list of test symbols.

    Args:
        count: Total number of symbols to generate
        include_vectors: If True, include vector symbols (VCTR|xxxx format)

    Returns:
        List of symbol strings

    Example:
        >>> symbols = generate_test_symbols(50)
        >>> len(symbols)
        50
        >>> 'sym0' in symbols
        True
    """
    symbols = []

    if include_vectors:
        # Half regular symbols, half vector symbols
        symbols.extend([f"sym{i}" for i in range(count // 2)])
        symbols.extend([f"VCTR|{i:04x}" for i in range(count // 2)])
    else:
        # All regular symbols
        symbols.extend([f"sym{i}" for i in range(count)])

    return symbols


def generate_test_sequence(length: int, vocab_size: int = 50) -> List[str]:
    """
    Generate a random sequence of symbols.

    Args:
        length: Length of sequence to generate
        vocab_size: Size of vocabulary to sample from

    Returns:
        List of symbols

    Example:
        >>> seq = generate_test_sequence(10)
        >>> len(seq)
        10
    """
    vocab = generate_test_symbols(vocab_size, include_vectors=True)
    return sorted(list(np.random.choice(vocab, min(length, vocab_size), replace=False)))


def flatten_pattern(pattern: List[List[str]]) -> List[str]:
    """
    Flatten pattern events into single list.

    Args:
        pattern: Pattern as list of events (each event is list of symbols)

    Returns:
        Flattened list of all symbols in pattern

    Example:
        >>> pattern = [['a', 'b'], ['c', 'd']]
        >>> flatten_pattern(pattern)
        ['a', 'b', 'c', 'd']
    """
    return list(chain(*pattern))


def create_overlapping_patterns(base_pattern: List[List[str]], num_variants: int = 3) -> List[List[List[str]]]:
    """
    Create variants of a pattern with partial overlap.

    Useful for testing matching algorithms with similar patterns.

    Args:
        base_pattern: Base pattern to create variants from
        num_variants: Number of variants to create

    Returns:
        List of pattern variants

    Example:
        >>> base = [['a', 'b'], ['c', 'd']]
        >>> variants = create_overlapping_patterns(base, num_variants=2)
        >>> len(variants)
        3  # base + 2 variants
    """
    variants = [base_pattern]

    for i in range(num_variants):
        variant = []
        for event in base_pattern:
            # Keep 50-80% of symbols, add some new ones
            keep_count = max(1, int(len(event) * (0.5 + np.random.rand() * 0.3)))
            kept_symbols = list(np.random.choice(event, keep_count, replace=False))

            # Add 1-2 new symbols
            new_count = np.random.randint(1, 3)
            new_symbols = [f"new{i}_{j}" for j in range(new_count)]

            variant.append(sorted(kept_symbols + new_symbols))

        variants.append(variant)

    return variants
