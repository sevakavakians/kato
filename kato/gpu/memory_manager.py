"""
GPU memory manager for pattern storage and retrieval.

Manages GPU VRAM allocation, pattern insertion, and retrieval for
high-performance pattern matching on CUDA-capable GPUs.
"""

import logging
from typing import List, Tuple, Optional, Dict, TYPE_CHECKING
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

from kato.config.gpu_settings import GPUConfig

logger = logging.getLogger(__name__)


class GPUMemoryManager:
    """
    Manages GPU memory for pattern storage.

    Features:
    - Pre-allocated buffers (no reallocation overhead)
    - Padded arrays for uniform GPU access
    - Batch insertion for efficiency
    - Memory usage tracking
    - Automatic capacity management

    Patterns are stored as:
    - gpu_patterns: [N × max_length] int32 array (padded with -1)
    - gpu_lengths: [N] int32 array (actual lengths)
    - pattern_names: List[str] (Python list, maps index → pattern hash)
    """

    def __init__(self, config: GPUConfig):
        """
        Initialize GPU memory manager.

        Args:
            config: GPU configuration

        Raises:
            RuntimeError: If GPU not available or insufficient memory
        """
        if not CUPY_AVAILABLE:
            raise RuntimeError("CuPy not available - GPU acceleration requires CuPy")

        self.config = config
        self.device = cp.cuda.Device()

        # Check GPU compatibility
        self._check_compatibility()

        # Calculate memory capacity
        self.max_capacity = self._calculate_max_capacity()

        # Initialize storage (pre-allocate)
        self._initialize_storage()

        # Track current usage
        self.pattern_count = 0
        self.pattern_name_to_idx: Dict[str, int] = {}

        if config.log_memory_usage:
            self._log_memory_usage("Initialization complete")

    def _check_compatibility(self) -> None:
        """Check if GPU meets minimum requirements."""
        props = self.device.attributes
        compute_cap = props['ComputeCapabilityMajor'] + props['ComputeCapabilityMinor'] / 10

        if compute_cap < self.config.min_compute_capability:
            raise RuntimeError(
                f"GPU compute capability {compute_cap} below minimum "
                f"{self.config.min_compute_capability}. Please use newer GPU."
            )

        logger.info(f"✓ GPU: {self.device.name}")
        logger.info(f"✓ Compute Capability: {compute_cap}")

    def _calculate_max_capacity(self) -> int:
        """
        Calculate maximum patterns that fit in available VRAM.

        Returns:
            Maximum number of patterns
        """
        # Check if capacity is forced (for testing)
        if self.config.force_max_patterns is not None:
            logger.info(f"Using forced max capacity: {self.config.force_max_patterns:,}")
            return self.config.force_max_patterns

        # Query available memory
        free_memory, total_memory = self.device.mem_info

        # Use fraction of free memory (safety margin)
        usable_memory = free_memory * self.config.memory_usage_fraction

        # Calculate pattern storage requirements
        bytes_per_pattern = self.config.max_pattern_length * 4  # int32
        bytes_per_length = 4  # int32

        # Include growth buffer
        effective_fraction = 1.0 + self.config.growth_buffer_fraction

        # Calculate capacity
        max_patterns = int(usable_memory / (bytes_per_pattern + bytes_per_length) / effective_fraction)

        logger.info(f"✓ Total VRAM: {total_memory / 1e9:.1f} GB")
        logger.info(f"✓ Free VRAM: {free_memory / 1e9:.1f} GB")
        logger.info(f"✓ Usable VRAM: {usable_memory / 1e9:.1f} GB ({self.config.memory_usage_fraction*100:.0f}%)")
        logger.info(f"✓ Max Patterns: {max_patterns:,}")

        return max_patterns

    def _initialize_storage(self) -> None:
        """Pre-allocate GPU arrays for pattern storage."""
        logger.info(f"Allocating GPU memory for {self.max_capacity:,} patterns...")

        # Allocate pattern array (padded to max_length)
        # Shape: [max_capacity, max_pattern_length]
        # Initialized with -1 (sentinel for padding)
        self.gpu_patterns = cp.full(
            (self.max_capacity, self.config.max_pattern_length),
            -1,
            dtype=cp.int32
        )

        # Allocate length array
        # Shape: [max_capacity]
        self.gpu_lengths = cp.zeros(self.max_capacity, dtype=cp.int32)

        # Pattern names (Python list on CPU)
        self.pattern_names: List[str] = []

        logger.info("✓ GPU memory allocated successfully")

    def add_pattern(self, pattern_name: str, encoded_sequence: np.ndarray) -> bool:
        """
        Add single pattern to GPU memory.

        Args:
            pattern_name: Pattern identifier (e.g., 'PTRN|abc123')
            encoded_sequence: Encoded symbol sequence (1D numpy array of int32)

        Returns:
            True if added, False if at capacity or duplicate

        Note:
            For batch insertion, use add_patterns_batch() for better performance.
        """
        # Check if already exists
        if pattern_name in self.pattern_name_to_idx:
            return False

        # Check capacity
        if self.pattern_count >= self.max_capacity:
            logger.warning(f"GPU memory at capacity ({self.max_capacity:,} patterns)")
            return False

        # Validate length
        if len(encoded_sequence) > self.config.max_pattern_length:
            logger.warning(
                f"Pattern {pattern_name} length {len(encoded_sequence)} exceeds "
                f"max {self.config.max_pattern_length}, truncating"
            )
            encoded_sequence = encoded_sequence[:self.config.max_pattern_length]

        # Get next available index
        idx = self.pattern_count

        # Copy pattern to GPU (with padding)
        pattern_length = len(encoded_sequence)
        self.gpu_patterns[idx, :pattern_length] = cp.asarray(encoded_sequence, dtype=cp.int32)
        # Rest is already -1 (padding)

        # Store length
        self.gpu_lengths[idx] = pattern_length

        # Store name mapping
        self.pattern_names.append(pattern_name)
        self.pattern_name_to_idx[pattern_name] = idx

        # Increment count
        self.pattern_count += 1

        return True

    def add_patterns_batch(self, patterns: List[Tuple[str, np.ndarray]]) -> int:
        """
        Add multiple patterns in batch (efficient).

        Args:
            patterns: List of (pattern_name, encoded_sequence) tuples

        Returns:
            Number of patterns successfully added

        Note:
            Batch insertion is ~10-20x faster than individual add_pattern() calls.
        """
        added_count = 0

        # Filter out duplicates and capacity check
        valid_patterns = []
        for pattern_name, encoded_sequence in patterns:
            if pattern_name in self.pattern_name_to_idx:
                continue  # Skip duplicates

            if self.pattern_count + len(valid_patterns) >= self.max_capacity:
                logger.warning(f"GPU memory at capacity, stopping batch insertion")
                break

            valid_patterns.append((pattern_name, encoded_sequence))

        if not valid_patterns:
            return 0

        # Prepare batch arrays
        batch_size = len(valid_patterns)
        batch_patterns = cp.full(
            (batch_size, self.config.max_pattern_length),
            -1,
            dtype=cp.int32
        )
        batch_lengths = cp.zeros(batch_size, dtype=cp.int32)

        # Fill batch arrays
        for i, (pattern_name, encoded_sequence) in enumerate(valid_patterns):
            # Truncate if needed
            if len(encoded_sequence) > self.config.max_pattern_length:
                encoded_sequence = encoded_sequence[:self.config.max_pattern_length]

            length = len(encoded_sequence)
            batch_patterns[i, :length] = cp.asarray(encoded_sequence, dtype=cp.int32)
            batch_lengths[i] = length

        # Insert batch into main arrays
        start_idx = self.pattern_count
        end_idx = start_idx + batch_size

        self.gpu_patterns[start_idx:end_idx, :] = batch_patterns
        self.gpu_lengths[start_idx:end_idx] = batch_lengths

        # Update name mappings
        for i, (pattern_name, _) in enumerate(valid_patterns):
            idx = start_idx + i
            self.pattern_names.append(pattern_name)
            self.pattern_name_to_idx[pattern_name] = idx

        # Update count
        self.pattern_count += batch_size
        added_count = batch_size

        logger.debug(f"Added {added_count:,} patterns in batch (total: {self.pattern_count:,})")

        return added_count

    def get_active_patterns(self) -> Tuple["cp.ndarray", "cp.ndarray", List[str]]:
        """
        Get currently stored patterns for matching.

        Returns:
            Tuple of:
            - gpu_patterns: [N × max_length] int32 array (active patterns only)
            - gpu_lengths: [N] int32 array (actual lengths)
            - pattern_names: List[str] (pattern identifiers)

        Note:
            Returns views (not copies) for efficiency.
        """
        if self.pattern_count == 0:
            # Return empty arrays
            return (
                cp.empty((0, self.config.max_pattern_length), dtype=cp.int32),
                cp.empty(0, dtype=cp.int32),
                []
            )

        # Return views of active portion
        return (
            self.gpu_patterns[:self.pattern_count],
            self.gpu_lengths[:self.pattern_count],
            self.pattern_names
        )

    def get_memory_usage_gb(self) -> float:
        """
        Get current GPU memory usage in GB.

        Returns:
            Memory used by this manager in GB
        """
        patterns_bytes = self.gpu_patterns.nbytes
        lengths_bytes = self.gpu_lengths.nbytes
        total_bytes = patterns_bytes + lengths_bytes
        return total_bytes / 1e9

    def get_capacity_info(self) -> Dict:
        """
        Get detailed capacity and usage information.

        Returns:
            Dictionary with capacity metrics
        """
        free_memory, total_memory = self.device.mem_info

        return {
            'pattern_count': self.pattern_count,
            'max_capacity': self.max_capacity,
            'utilization': self.pattern_count / self.max_capacity if self.max_capacity > 0 else 0.0,
            'memory_used_gb': self.get_memory_usage_gb(),
            'vram_free_gb': free_memory / 1e9,
            'vram_total_gb': total_memory / 1e9,
        }

    def clear(self) -> None:
        """Clear all patterns (reset to empty state)."""
        self.pattern_count = 0
        self.pattern_names.clear()
        self.pattern_name_to_idx.clear()

        # Reset arrays (fill with -1/0)
        self.gpu_patterns.fill(-1)
        self.gpu_lengths.fill(0)

        logger.info("GPU memory cleared")

    def _log_memory_usage(self, context: str = "") -> None:
        """Log current memory usage."""
        info = self.get_capacity_info()

        logger.info(
            f"GPU Memory ({context}): "
            f"{info['pattern_count']:,}/{info['max_capacity']:,} patterns "
            f"({info['utilization']*100:.1f}% full), "
            f"{info['memory_used_gb']:.2f} GB used, "
            f"{info['vram_free_gb']:.1f}/{info['vram_total_gb']:.1f} GB VRAM"
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"GPUMemoryManager("
            f"patterns={self.pattern_count:,}/{self.max_capacity:,}, "
            f"memory={self.get_memory_usage_gb():.2f}GB)"
        )
