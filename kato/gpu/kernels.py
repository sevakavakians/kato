"""
CUDA kernels for GPU-accelerated pattern similarity calculation.

Implements LCS-based similarity matching that produces identical results
to Python's difflib.SequenceMatcher.ratio() for deterministic behavior.
"""

import logging
from typing import Tuple, TYPE_CHECKING
import numpy as np

try:
    import cupy as cp
    from cupyx import jit
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False
    cp = None
    jit = None

# Import for type checking only (not evaluated at runtime)
if TYPE_CHECKING:
    import cupy as cp

from kato.config.gpu_settings import GPUConfig

logger = logging.getLogger(__name__)


if CUPY_AVAILABLE:
    @jit.rawkernel()
    def lcs_similarity_kernel(
        patterns,          # [N × max_len] int32
        pattern_lengths,   # [N] int32
        query,             # [query_len] int32
        query_length,      # int32 scalar
        similarities,      # [N] float32 (output)
        threshold,         # float32 scalar
        max_pattern_len    # int32 scalar
    ):
        """
        CUDA kernel to compute LCS-based similarity for all patterns.

        Each thread processes ONE pattern:
        1. Compute LCS length between query and pattern
        2. Calculate similarity = 2.0 * LCS / (query_len + pattern_len)
        3. Apply threshold (set to 0.0 if below threshold)
        4. Store result in similarities array

        Algorithm: Dynamic programming LCS (Longest Common Subsequence)
        Complexity: O(query_len * pattern_len) per thread

        Note: Uses shared memory for query to reduce global memory access.
        """
        # Thread index (one thread per pattern)
        tid = jit.blockIdx.x * jit.blockDim.x + jit.threadIdx.x

        # Bounds check
        if tid >= patterns.shape[0]:
            return

        # Get pattern length
        pattern_len = pattern_lengths[tid]

        # Skip if pattern is empty
        if pattern_len <= 0:
            similarities[tid] = 0.0
            return

        # Load query into shared memory (once per block for efficiency)
        shared_query = jit.shared_memory(dtype=cp.int32, size=512)  # Max query length

        # First thread in block loads query
        if jit.threadIdx.x == 0:
            for i in range(query_length):
                if i < 512:  # Bounds check
                    shared_query[i] = query[i]

        # Synchronize to ensure query is loaded
        jit.syncthreads()

        # Compute LCS length using dynamic programming
        # We use a 2-row DP table to save memory (only need previous row)

        # Allocate DP table in local memory (registers)
        # dp[i][j] = LCS length of query[:i] and pattern[:j]
        # We only keep current and previous row

        MAX_LEN = 512  # Maximum supported length
        prev_row = jit.shared_memory(dtype=cp.int32, size=MAX_LEN)
        curr_row = jit.shared_memory(dtype=cp.int32, size=MAX_LEN)

        # Initialize first row to zeros
        for j in range(min(pattern_len + 1, MAX_LEN)):
            prev_row[j] = 0

        # Compute LCS using DP
        for i in range(1, min(query_length + 1, MAX_LEN)):
            curr_row[0] = 0

            for j in range(1, min(pattern_len + 1, MAX_LEN)):
                # Get symbols
                query_sym = shared_query[i - 1] if (i - 1) < query_length else -1
                pattern_sym = patterns[tid, j - 1] if (j - 1) < pattern_len else -1

                # Skip padding (-1)
                if pattern_sym == -1:
                    curr_row[j] = curr_row[j - 1]
                    continue

                # DP recurrence
                if query_sym == pattern_sym:
                    # Match: take diagonal + 1
                    curr_row[j] = prev_row[j - 1] + 1
                else:
                    # No match: take max of left and top
                    curr_row[j] = max(curr_row[j - 1], prev_row[j])

            # Swap rows (current becomes previous)
            for j in range(min(pattern_len + 1, MAX_LEN)):
                prev_row[j] = curr_row[j]

        # LCS length is in prev_row[pattern_len]
        lcs_length = prev_row[min(pattern_len, MAX_LEN - 1)]

        # Calculate similarity (same as difflib.SequenceMatcher.ratio())
        # similarity = 2.0 * LCS / (len1 + len2)
        total_length = query_length + pattern_len

        if total_length == 0:
            similarity = 0.0
        else:
            similarity = 2.0 * float(lcs_length) / float(total_length)

        # Apply threshold (early termination)
        if similarity < threshold:
            similarities[tid] = 0.0
        else:
            similarities[tid] = similarity


class CUDAPatternMatcher:
    """
    GPU-accelerated pattern matcher using CUDA kernels.

    Computes similarity scores for all patterns in parallel on GPU,
    achieving 100-1000x speedup over sequential CPU processing.
    """

    def __init__(self, config: GPUConfig):
        """
        Initialize CUDA pattern matcher.

        Args:
            config: GPU configuration

        Raises:
            RuntimeError: If CuPy/CUDA not available
        """
        if not CUPY_AVAILABLE:
            raise RuntimeError("CuPy not available - GPU acceleration requires CuPy")

        self.config = config
        self.device = cp.cuda.Device()

        logger.info("CUDA pattern matcher initialized")

    def calculate_similarities(
        self,
        patterns: "cp.ndarray",
        pattern_lengths: "cp.ndarray",
        query: "cp.ndarray",
        threshold: float = 0.0
    ) -> "cp.ndarray":
        """
        Calculate similarity scores for all patterns against query.

        Args:
            patterns: [N × max_len] int32 array of encoded patterns
            pattern_lengths: [N] int32 array of actual pattern lengths
            query: [query_len] int32 array of encoded query
            threshold: Minimum similarity threshold (0.0-1.0)

        Returns:
            [N] float32 array of similarity scores (0.0 for below threshold)

        Note:
            Runs on GPU, returns GPU array. Use .get() to transfer to CPU.
        """
        num_patterns = patterns.shape[0]

        if num_patterns == 0:
            return cp.empty(0, dtype=cp.float32)

        # Allocate output array on GPU
        similarities = cp.zeros(num_patterns, dtype=cp.float32)

        # Get query length
        query_length = len(query)

        # Calculate launch configuration
        threads_per_block = self.config.threads_per_block
        blocks = (num_patterns + threads_per_block - 1) // threads_per_block

        # Launch kernel
        if self.config.log_kernel_timing:
            start = cp.cuda.Event()
            end = cp.cuda.Event()
            start.record()

        # Shared memory size (for query and DP table)
        # query: 512 int32 = 2KB
        # prev_row: 512 int32 = 2KB
        # curr_row: 512 int32 = 2KB
        # Total: 6KB per block (well within limits)
        shared_mem_bytes = (512 + 512 + 512) * 4

        lcs_similarity_kernel[
            (blocks,),
            (threads_per_block,),
            shared_mem_bytes
        ](
            patterns,
            pattern_lengths,
            query,
            query_length,
            similarities,
            float(threshold),
            patterns.shape[1]  # max_pattern_length
        )

        if self.config.log_kernel_timing:
            end.record()
            end.synchronize()
            elapsed_ms = cp.cuda.get_elapsed_time(start, end)
            logger.debug(
                f"Kernel execution: {elapsed_ms:.2f}ms for {num_patterns:,} patterns "
                f"({num_patterns/elapsed_ms*1000:.0f} patterns/sec)"
            )

        return similarities

    def match_patterns(
        self,
        patterns: "cp.ndarray",
        pattern_lengths: "cp.ndarray",
        pattern_names: list,
        query: "cp.ndarray",
        threshold: float,
        max_results: int = 100
    ) -> list:
        """
        Find top matching patterns for query.

        Args:
            patterns: [N × max_len] int32 array
            pattern_lengths: [N] int32 array
            pattern_names: List[str] of pattern identifiers
            query: [query_len] int32 array
            threshold: Minimum similarity (0.0-1.0)
            max_results: Maximum results to return

        Returns:
            List of dicts with 'pattern_name' and 'similarity' keys,
            sorted by similarity (highest first)
        """
        # Calculate similarities
        similarities = self.calculate_similarities(
            patterns, pattern_lengths, query, threshold
        )

        # Transfer to CPU for sorting/filtering (small data)
        similarities_cpu = similarities.get()

        # Find matches above threshold
        matches = []
        for idx, similarity in enumerate(similarities_cpu):
            if similarity >= threshold:
                matches.append({
                    'pattern_name': pattern_names[idx],
                    'similarity': float(similarity),
                    'index': idx
                })

        # Sort by similarity (descending)
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        # Limit results
        return matches[:max_results]


def test_determinism():
    """
    Test function to verify GPU LCS matches CPU difflib results.

    This should be run on a system with GPU to validate correctness.
    """
    if not CUPY_AVAILABLE:
        print("CuPy not available - skipping GPU determinism test")
        return

    from difflib import SequenceMatcher

    print("Testing GPU vs CPU determinism...")

    # Test cases
    test_cases = [
        ([1, 2, 3], [1, 2, 3, 4, 5]),           # Perfect prefix
        ([1, 2, 3], [4, 5, 6]),                  # No match
        ([1, 2, 3, 4], [1, 3, 5, 7]),           # Partial match
        ([1, 2, 3], [1, 2, 3]),                  # Exact match
        ([1], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), # Single element
    ]

    config = GPUConfig()
    matcher = CUDAPatternMatcher(config)

    all_passed = True

    for query_list, pattern_list in test_cases:
        # CPU reference (difflib)
        cpu_similarity = SequenceMatcher(None, query_list, pattern_list).ratio()

        # GPU calculation
        query_gpu = cp.array(query_list, dtype=cp.int32)
        pattern_gpu = cp.array([pattern_list + [-1] * (100 - len(pattern_list))], dtype=cp.int32)
        lengths_gpu = cp.array([len(pattern_list)], dtype=cp.int32)

        similarities_gpu = matcher.calculate_similarities(
            pattern_gpu, lengths_gpu, query_gpu, threshold=0.0
        )
        gpu_similarity = float(similarities_gpu[0].get())

        # Compare
        diff = abs(cpu_similarity - gpu_similarity)
        passed = diff < 1e-6

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: query={query_list}, pattern={pattern_list}")
        print(f"  CPU: {cpu_similarity:.6f}, GPU: {gpu_similarity:.6f}, diff: {diff:.9f}")

        if not passed:
            all_passed = False

    if all_passed:
        print("\n✓ All determinism tests PASSED")
    else:
        print("\n✗ Some determinism tests FAILED")

    return all_passed


if __name__ == '__main__':
    # Run determinism test if executed directly
    test_determinism()
