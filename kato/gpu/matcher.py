"""
Hybrid GPU+CPU pattern matcher with dual-tier architecture.

Combines GPU tier (bulk stable patterns) with CPU tier (recently learned patterns)
for optimal performance and real-time learning capability.
"""

import logging
import time
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING
import numpy as np

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False
    cp = None

# Import for type checking only (not evaluated at runtime)
if TYPE_CHECKING:
    import cupy as cp

from kato.gpu.encoder import SymbolVocabularyEncoder
from kato.gpu.memory_manager import GPUMemoryManager
from kato.gpu.kernels import CUDAPatternMatcher
from kato.config.gpu_settings import GPUConfig

logger = logging.getLogger(__name__)


class HybridGPUMatcher:
    """
    Hybrid GPU+CPU pattern matcher.

    Architecture:
    - GPU Tier: Millions of stable patterns, batch updates, 50-100ms queries
    - CPU Tier: 0-10K recent patterns, instant insertion, 5-10ms queries
    - Automatic promotion: CPU → GPU when threshold reached

    Query flow:
    1. Query GPU tier (bulk patterns in parallel)
    2. Query CPU tier (recent patterns with RapidFuzz)
    3. Merge results (union, deduplicate, sort)

    Learning flow:
    1. Add to CPU tier (instant, <1ms)
    2. Check sync triggers
    3. Promote to GPU tier in background (async)
    """

    def __init__(
        self,
        encoder: SymbolVocabularyEncoder,
        config: GPUConfig,
        patterns_cache: Optional[Dict] = None
    ):
        """
        Initialize hybrid GPU+CPU matcher.

        Args:
            encoder: Symbol vocabulary encoder (shared instance)
            config: GPU configuration
            patterns_cache: Existing patterns cache (for CPU tier fallback)

        Raises:
            RuntimeError: If GPU not available and fallback disabled
        """
        self.encoder = encoder
        self.config = config
        self.use_gpu = False

        # Check GPU availability
        if not CUPY_AVAILABLE:
            if not config.fallback_to_cpu:
                raise RuntimeError("CuPy not available and fallback disabled")
            logger.warning("CuPy not available, GPU acceleration disabled")
            return

        try:
            # Initialize GPU components
            self.memory_manager = GPUMemoryManager(config)
            self.cuda_matcher = CUDAPatternMatcher(config)
            self.use_gpu = True

            logger.info("✓ GPU acceleration enabled")

        except Exception as e:
            if not config.fallback_to_cpu:
                raise

            logger.warning(f"GPU initialization failed: {e}, using CPU fallback")
            return

        # CPU tier: Recently learned patterns (not yet on GPU)
        # Format: {pattern_name: encoded_sequence}
        self.cpu_tier: Dict[str, np.ndarray] = {}

        # Track sync status
        self.last_sync_time = time.time()
        self.patterns_since_sync = 0

        # Statistics
        self.stats = {
            'gpu_queries': 0,
            'cpu_queries': 0,
            'patterns_learned': 0,
            'syncs_triggered': 0,
        }

    def match_patterns(
        self,
        state: List[str],
        threshold: float,
        max_predictions: int = 100
    ) -> List[Dict]:
        """
        Find matching patterns for given state.

        Args:
            state: Flattened STM state (list of symbols)
            threshold: Minimum similarity (0.0-1.0)
            max_predictions: Maximum results to return

        Returns:
            List of dicts with 'pattern_name' and 'similarity' keys,
            sorted by similarity descending
        """
        if not self.use_gpu:
            # GPU not available, caller should use CPU fallback
            return []

        # Encode query
        query_encoded = self.encoder.encode_sequence(state)
        query_gpu = cp.asarray(query_encoded, dtype=cp.int32)

        results = []

        # Query GPU tier (bulk patterns)
        if self.memory_manager.pattern_count > 0:
            gpu_results = self._query_gpu_tier(query_gpu, threshold, max_predictions)
            results.extend(gpu_results)
            self.stats['gpu_queries'] += 1

        # Query CPU tier (recent patterns)
        if len(self.cpu_tier) > 0:
            cpu_results = self._query_cpu_tier(query_encoded, state, threshold, max_predictions)
            results.extend(cpu_results)
            self.stats['cpu_queries'] += 1

        # Merge and deduplicate
        results = self._merge_results(results)

        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)

        # Limit results
        return results[:max_predictions]

    def _query_gpu_tier(
        self,
        query_gpu: "cp.ndarray",
        threshold: float,
        max_results: int
    ) -> List[Dict]:
        """
        Query GPU tier for matching patterns.

        Args:
            query_gpu: Encoded query on GPU
            threshold: Minimum similarity
            max_results: Maximum results

        Returns:
            List of matches with pattern_name and similarity
        """
        # Get active patterns from GPU
        patterns, lengths, pattern_names = self.memory_manager.get_active_patterns()

        if len(pattern_names) == 0:
            return []

        # Run CUDA kernel
        matches = self.cuda_matcher.match_patterns(
            patterns=patterns,
            pattern_lengths=lengths,
            pattern_names=pattern_names,
            query=query_gpu,
            threshold=threshold,
            max_results=max_results
        )

        return matches

    def _query_cpu_tier(
        self,
        query_encoded: np.ndarray,
        query_original: List[str],
        threshold: float,
        max_results: int
    ) -> List[Dict]:
        """
        Query CPU tier using sequence matcher.

        Args:
            query_encoded: Encoded query (numpy array)
            query_original: Original query symbols (for debugging)
            threshold: Minimum similarity
            max_results: Maximum results

        Returns:
            List of matches with pattern_name and similarity

        Note:
            Uses Python's difflib for CPU matching (slow but correct).
            Could be optimized with RapidFuzz, but CPU tier is small (<10K patterns).
        """
        from difflib import SequenceMatcher

        matches = []

        for pattern_name, pattern_encoded in self.cpu_tier.items():
            # Calculate similarity using SequenceMatcher
            # (Same algorithm as GPU kernel for determinism)
            matcher = SequenceMatcher(None, query_encoded.tolist(), pattern_encoded.tolist())
            similarity = matcher.ratio()

            if similarity >= threshold:
                matches.append({
                    'pattern_name': pattern_name,
                    'similarity': float(similarity)
                })

        # Sort by similarity
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        return matches[:max_results]

    def _merge_results(self, results: List[Dict]) -> List[Dict]:
        """
        Merge results from GPU and CPU tiers, removing duplicates.

        Args:
            results: Combined results from both tiers

        Returns:
            Deduplicated results (keeps highest similarity for duplicates)
        """
        # Use dict to deduplicate (pattern_name → best match)
        best_matches: Dict[str, Dict] = {}

        for match in results:
            pattern_name = match['pattern_name']

            if pattern_name not in best_matches:
                best_matches[pattern_name] = match
            else:
                # Keep higher similarity
                if match['similarity'] > best_matches[pattern_name]['similarity']:
                    best_matches[pattern_name] = match

        return list(best_matches.values())

    def add_new_pattern(
        self,
        pattern_name: str,
        pattern_sequence: List[List[str]]
    ) -> bool:
        """
        Add newly learned pattern.

        Args:
            pattern_name: Pattern identifier (e.g., 'PTRN|abc123')
            pattern_sequence: Pattern as list of events (list of symbol lists)

        Returns:
            True if added successfully

        Note:
            Pattern goes to CPU tier first (instant insertion).
            Will be promoted to GPU tier on next sync.
        """
        if not self.use_gpu:
            return False

        # Flatten pattern sequence
        flattened = []
        for event in pattern_sequence:
            flattened.extend(event)

        # Encode pattern
        try:
            encoded = self.encoder.encode_sequence(flattened)
        except Exception as e:
            logger.warning(f"Failed to encode pattern {pattern_name}: {e}")
            return False

        # Check if already exists (GPU or CPU tier)
        if pattern_name in self.cpu_tier:
            return False  # Already in CPU tier

        if pattern_name in self.memory_manager.pattern_name_to_idx:
            return False  # Already in GPU tier

        # Add to CPU tier
        self.cpu_tier[pattern_name] = encoded

        # Update stats
        self.stats['patterns_learned'] += 1
        self.patterns_since_sync += 1

        logger.debug(f"Added pattern {pattern_name} to CPU tier ({len(self.cpu_tier)} total)")

        return True

    def check_sync_needed(self) -> bool:
        """
        Check if sync should be triggered.

        Sync triggers:
        1. CPU tier size exceeds threshold
        2. Time since last sync exceeds interval (background sync)

        Returns:
            True if sync should be triggered
        """
        if not self.use_gpu:
            return False

        # Trigger 1: CPU tier size threshold
        if len(self.cpu_tier) >= self.config.sync_threshold:
            logger.info(f"Sync trigger: CPU tier at {len(self.cpu_tier)} patterns")
            return True

        # Trigger 2: Time-based
        if self.config.enable_background_sync:
            elapsed = time.time() - self.last_sync_time
            if elapsed >= self.config.sync_interval_seconds:
                if len(self.cpu_tier) > 0:  # Only sync if there are patterns
                    logger.info(f"Sync trigger: {elapsed:.0f}s since last sync")
                    return True

        return False

    def sync_cpu_to_gpu(self) -> int:
        """
        Synchronize CPU tier patterns to GPU tier.

        Promotes all patterns from CPU tier to GPU tier in batch.

        Returns:
            Number of patterns synchronized

        Note:
            This operation takes ~100ms for 1000 patterns.
            Queries continue to work during sync (CPU tier still available).
        """
        if not self.use_gpu or len(self.cpu_tier) == 0:
            return 0

        sync_start = time.time()

        # Prepare batch for GPU
        patterns_to_sync = [(name, encoded) for name, encoded in self.cpu_tier.items()]

        # Add to GPU in batch
        added_count = self.memory_manager.add_patterns_batch(patterns_to_sync)

        # Clear CPU tier (patterns now on GPU)
        self.cpu_tier.clear()

        # Update stats
        self.stats['syncs_triggered'] += 1
        self.last_sync_time = time.time()
        self.patterns_since_sync = 0

        sync_duration = time.time() - sync_start

        logger.info(
            f"Synced {added_count:,} patterns to GPU in {sync_duration*1000:.1f}ms "
            f"(GPU total: {self.memory_manager.pattern_count:,})"
        )

        if self.config.log_memory_usage:
            self.memory_manager._log_memory_usage("After sync")

        return added_count

    def get_stats(self) -> Dict:
        """
        Get matcher statistics.

        Returns:
            Dictionary with performance and usage metrics
        """
        base_stats = {
            'use_gpu': self.use_gpu,
            'gpu_tier_patterns': self.memory_manager.pattern_count if self.use_gpu else 0,
            'cpu_tier_patterns': len(self.cpu_tier),
            'total_patterns': (
                (self.memory_manager.pattern_count if self.use_gpu else 0) +
                len(self.cpu_tier)
            ),
            **self.stats
        }

        if self.use_gpu:
            capacity_info = self.memory_manager.get_capacity_info()
            base_stats.update({
                'gpu_capacity': capacity_info['max_capacity'],
                'gpu_utilization': capacity_info['utilization'],
                'gpu_memory_gb': capacity_info['memory_used_gb'],
            })

        return base_stats

    def clear_all(self) -> None:
        """Clear both GPU and CPU tiers."""
        if self.use_gpu:
            self.memory_manager.clear()

        self.cpu_tier.clear()
        self.last_sync_time = time.time()
        self.patterns_since_sync = 0

        logger.info("Cleared all patterns (GPU + CPU tiers)")

    def __repr__(self) -> str:
        """String representation for debugging."""
        if not self.use_gpu:
            return "HybridGPUMatcher(gpu=disabled)"

        return (
            f"HybridGPUMatcher("
            f"gpu={self.memory_manager.pattern_count:,}, "
            f"cpu={len(self.cpu_tier):,})"
        )
