"""
GPU configuration settings for KATO pattern matching acceleration.

This module defines configuration for GPU-accelerated pattern matching,
with automatic adaptation to available hardware.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUConfig:
    """
    GPU configuration that adapts to any CUDA-capable GPU.

    All settings have sensible defaults that work across different GPU models.
    Runtime detection fills in hardware-specific values (memory, compute capability).
    """

    # Feature flags
    enabled: bool = True
    """Enable GPU acceleration if available (fallback to CPU if not)."""

    fallback_to_cpu: bool = True
    """Use CPU (RapidFuzz) if GPU unavailable or errors occur."""

    # Hardware requirements
    min_compute_capability: float = 7.0
    """Minimum CUDA compute capability (7.0 = Volta or newer)."""

    # Memory management
    max_pattern_length: int = 100
    """Maximum symbols per pattern (patterns padded/truncated to this length)."""

    memory_usage_fraction: float = 0.6
    """Fraction of free VRAM to use (0.6 = 60% for safety margin)."""

    growth_buffer_fraction: float = 0.2
    """Extra capacity for growth (0.2 = 20% additional patterns)."""

    # Kernel configuration (universal defaults)
    threads_per_block: int = 256
    """Threads per block for CUDA kernels (256 works well on all modern GPUs)."""

    # Pattern capacity override (for testing)
    force_max_patterns: Optional[int] = None
    """Override auto-detected pattern capacity (None = auto-detect based on VRAM)."""

    # Sync configuration (CPU tier → GPU tier promotion)
    sync_threshold: int = 1000
    """Trigger sync after this many patterns in CPU tier."""

    sync_interval_seconds: int = 300
    """Background sync interval (300 = 5 minutes)."""

    enable_background_sync: bool = True
    """Enable periodic background sync (recommended)."""

    # Monitoring
    log_memory_usage: bool = True
    """Log GPU memory usage at startup and after sync."""

    log_kernel_timing: bool = False
    """Log detailed kernel execution timing (for debugging/profiling)."""

    # Performance tuning
    use_shared_memory: bool = True
    """Use shared memory for query in CUDA kernel (faster, recommended)."""

    enable_early_termination: bool = True
    """Skip patterns below threshold during kernel execution (faster)."""

    @classmethod
    def from_env(cls) -> 'GPUConfig':
        """
        Create GPU configuration from environment variables.

        Environment variables:
            KATO_GPU_ENABLED: Enable GPU (true/false)
            KATO_GPU_MIN_COMPUTE: Minimum compute capability (float)
            KATO_GPU_MAX_PATTERN_LENGTH: Max pattern length (int)
            KATO_GPU_MEMORY_FRACTION: VRAM usage fraction (float)
            KATO_GPU_SYNC_THRESHOLD: CPU→GPU sync threshold (int)
            KATO_GPU_SYNC_INTERVAL: Background sync interval seconds (int)
            KATO_GPU_MAX_PATTERNS: Force max patterns (int, optional)

        Returns:
            GPUConfig with values from environment or defaults
        """
        def get_bool(key: str, default: bool) -> bool:
            value = os.getenv(key, str(default)).lower()
            return value in ('true', '1', 'yes', 'on')

        def get_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default

        def get_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                return default

        def get_optional_int(key: str) -> Optional[int]:
            value = os.getenv(key)
            if value is None:
                return None
            try:
                return int(value)
            except ValueError:
                return None

        return cls(
            enabled=get_bool('KATO_GPU_ENABLED', True),
            fallback_to_cpu=get_bool('KATO_GPU_FALLBACK', True),
            min_compute_capability=get_float('KATO_GPU_MIN_COMPUTE', 7.0),
            max_pattern_length=get_int('KATO_GPU_MAX_PATTERN_LENGTH', 100),
            memory_usage_fraction=get_float('KATO_GPU_MEMORY_FRACTION', 0.6),
            growth_buffer_fraction=get_float('KATO_GPU_GROWTH_FRACTION', 0.2),
            threads_per_block=get_int('KATO_GPU_THREADS_PER_BLOCK', 256),
            force_max_patterns=get_optional_int('KATO_GPU_MAX_PATTERNS'),
            sync_threshold=get_int('KATO_GPU_SYNC_THRESHOLD', 1000),
            sync_interval_seconds=get_int('KATO_GPU_SYNC_INTERVAL', 300),
            enable_background_sync=get_bool('KATO_GPU_BACKGROUND_SYNC', True),
            log_memory_usage=get_bool('KATO_GPU_LOG_MEMORY', True),
            log_kernel_timing=get_bool('KATO_GPU_LOG_TIMING', False),
            use_shared_memory=get_bool('KATO_GPU_SHARED_MEMORY', True),
            enable_early_termination=get_bool('KATO_GPU_EARLY_TERM', True),
        )

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If configuration is invalid
        """
        if self.max_pattern_length <= 0:
            raise ValueError("max_pattern_length must be positive")

        if not 0.0 < self.memory_usage_fraction <= 1.0:
            raise ValueError("memory_usage_fraction must be in (0.0, 1.0]")

        if not 0.0 <= self.growth_buffer_fraction <= 1.0:
            raise ValueError("growth_buffer_fraction must be in [0.0, 1.0]")

        if self.threads_per_block <= 0 or self.threads_per_block % 32 != 0:
            raise ValueError("threads_per_block must be positive and multiple of 32")

        if self.threads_per_block > 1024:
            raise ValueError("threads_per_block cannot exceed 1024 (GPU hardware limit)")

        if self.sync_threshold <= 0:
            raise ValueError("sync_threshold must be positive")

        if self.sync_interval_seconds <= 0:
            raise ValueError("sync_interval_seconds must be positive")

        if self.min_compute_capability < 3.0:
            raise ValueError("min_compute_capability too low (need at least 3.0)")

    def __str__(self) -> str:
        """Return human-readable configuration summary."""
        return (
            f"GPUConfig(\n"
            f"  enabled={self.enabled}\n"
            f"  min_compute_capability={self.min_compute_capability}\n"
            f"  max_pattern_length={self.max_pattern_length}\n"
            f"  memory_usage_fraction={self.memory_usage_fraction}\n"
            f"  threads_per_block={self.threads_per_block}\n"
            f"  sync_threshold={self.sync_threshold}\n"
            f"  sync_interval={self.sync_interval_seconds}s\n"
            f")"
        )


# Default configuration instance
DEFAULT_GPU_CONFIG = GPUConfig()
