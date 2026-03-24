"""
Realistic test data generator for KATO performance benchmarks.

Generates patterns and observations at configurable scale tiers with
Zipf-distributed vocabulary to simulate realistic token overlap.

Usage:
    from benchmarks.data_generator import BenchmarkDataGenerator

    gen = BenchmarkDataGenerator(seed=42)
    patterns = gen.generate_patterns(count=1000)
    observations = gen.generate_observations(patterns, count=50)
"""

import random
import uuid
from itertools import chain
from typing import Any

from kato.representations.pattern import Pattern


# Scale tier presets
SCALE_TIERS = {
    100: "bench_100",
    1_000: "bench_1k",
    10_000: "bench_10k",
    100_000: "bench_100k",
}


class BenchmarkDataGenerator:
    """Generates realistic test data for KATO benchmarks."""

    def __init__(self, seed: int = 42, vocab_size: int = 200, vector_token_count: int = 50):
        """
        Initialize generator with reproducible randomness.

        Args:
            seed: Random seed for reproducibility
            vocab_size: Total vocabulary size (word tokens + vector tokens)
            vector_token_count: Number of VCTR| tokens in vocabulary
        """
        self.seed = seed
        self.rng = random.Random(seed)
        self.vocab_size = vocab_size
        self.vector_token_count = vector_token_count

        # Build vocabulary: word-like tokens + vector hash tokens
        word_count = vocab_size - vector_token_count
        self.word_tokens = [f"tok_{i}" for i in range(word_count)]
        self.vector_tokens = [f"VCTR|{i:04x}" for i in range(vector_token_count)]
        self.vocab = self.word_tokens + self.vector_tokens

        # Zipf weights for realistic token frequency distribution
        # Lower-indexed tokens are much more common (power law)
        self.zipf_weights = [1.0 / (i + 1) ** 0.8 for i in range(len(self.vocab))]

    def _weighted_sample(self, k: int) -> list[str]:
        """Sample k unique tokens using Zipf weights (without replacement)."""
        # random.choices allows duplicates, so sample more and deduplicate
        sampled = set()
        attempts = 0
        while len(sampled) < k and attempts < k * 5:
            tokens = self.rng.choices(self.vocab, weights=self.zipf_weights, k=min(k * 2, len(self.vocab)))
            sampled.update(tokens)
            attempts += 1
        result = list(sampled)[:k]
        result.sort()  # KATO sorts tokens within events for token-level matching
        return result

    def generate_patterns(self, count: int,
                          min_events: int = 2, max_events: int = 5,
                          min_tokens_per_event: int = 3,
                          max_tokens_per_event: int = 15) -> list[Pattern]:
        """
        Generate realistic patterns.

        Args:
            count: Number of patterns to generate
            min_events: Minimum events per pattern
            max_events: Maximum events per pattern
            min_tokens_per_event: Minimum tokens per event
            max_tokens_per_event: Maximum tokens per event

        Returns:
            List of Pattern objects
        """
        patterns = []
        for _ in range(count):
            num_events = self.rng.randint(min_events, max_events)
            events = []
            for _ in range(num_events):
                event_size = self.rng.randint(min_tokens_per_event, max_tokens_per_event)
                event = self._weighted_sample(event_size)
                events.append(event)
            patterns.append(Pattern(events))
        return patterns

    def generate_observations(self, patterns: list[Pattern], count: int,
                              overlap_min: float = 0.3,
                              overlap_max: float = 0.7,
                              min_stm_events: int = 1,
                              max_stm_events: int = 10) -> list[dict]:
        """
        Generate observation STM states that partially overlap learned patterns.

        Each observation is a list of events (STM state) designed to have
        configurable overlap with existing patterns — exercises the matching path.

        Args:
            patterns: Learned patterns to base observations on
            count: Number of observations to generate
            overlap_min: Minimum token overlap ratio with source pattern
            overlap_max: Maximum token overlap ratio with source pattern
            min_stm_events: Minimum events in STM
            max_stm_events: Maximum events in STM

        Returns:
            List of dicts with 'stm' (list of events) and 'source_pattern_name'
        """
        observations = []
        for _ in range(count):
            # Pick a random source pattern
            source = self.rng.choice(patterns)
            overlap_ratio = self.rng.uniform(overlap_min, overlap_max)

            # Determine STM size
            num_events = self.rng.randint(
                min(min_stm_events, len(source.pattern_data)),
                min(max_stm_events, len(source.pattern_data))
            )

            # Build STM with partial overlap
            stm_events = []
            source_events = source.pattern_data[:num_events]

            for event in source_events:
                # Keep a fraction of tokens from the source event
                keep_count = max(1, int(len(event) * overlap_ratio))
                kept_tokens = self.rng.sample(event, min(keep_count, len(event)))

                # Add some noise tokens
                noise_count = self.rng.randint(0, 3)
                noise_tokens = self._weighted_sample(noise_count + len(event))
                noise_tokens = [t for t in noise_tokens if t not in kept_tokens][:noise_count]

                combined = sorted(set(kept_tokens + noise_tokens))
                stm_events.append(combined)

            observations.append({
                "stm": stm_events,
                "stm_flat": list(chain(*stm_events)),
                "source_pattern_name": source.name,
                "num_events": num_events,
            })

        return observations

    def generate_single_symbol_queries(self, patterns: list[Pattern],
                                        count: int) -> list[dict]:
        """
        Generate single-symbol queries for testing the fast prediction path.

        Picks tokens that appear in at least one pattern's first event.

        Args:
            patterns: Learned patterns
            count: Number of queries to generate

        Returns:
            List of dicts with 'symbol' and 'expected_patterns' count
        """
        # Collect first tokens from all patterns
        first_tokens = {}
        for p in patterns:
            if p.pattern_data and p.pattern_data[0]:
                for token in p.pattern_data[0]:
                    if token not in first_tokens:
                        first_tokens[token] = 0
                    first_tokens[token] += 1

        if not first_tokens:
            return []

        token_list = list(first_tokens.keys())
        queries = []
        for _ in range(count):
            token = self.rng.choice(token_list)
            queries.append({
                "symbol": token,
                "stm": [[token]],
                "stm_flat": [token],
                "expected_pattern_count": first_tokens[token],
            })

        return queries

    @staticmethod
    def make_processor_id(tier_size: int) -> str:
        """Generate a unique processor_id for a given tier size.

        Args:
            tier_size: Number of patterns (100, 1000, 10000, 100000)

        Returns:
            Unique processor ID string
        """
        prefix = SCALE_TIERS.get(tier_size, f"bench_{tier_size}")
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
