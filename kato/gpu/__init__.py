"""
GPU acceleration module for KATO pattern matching.

This module provides GPU-accelerated pattern matching using CUDA/CuPy.

Status: Phase 1 & 2 Complete, Phase 3 Implementation Ready

Phase 1 (✅ Complete): Foundation & Profiling
- SymbolVocabularyEncoder: String ↔ integer mapping with MongoDB persistence

Phase 2 (✅ Complete): CPU Optimization
- RapidFuzz integration for 8-10x speedup

Phase 3 (🚀 Ready): GPU Core Implementation
- GPUMemoryManager: VRAM management and pattern storage
- CUDAPatternMatcher: CUDA kernels for parallel similarity computation
- HybridGPUMatcher: Dual-tier architecture (GPU + CPU)
- SyncManager: CPU → GPU synchronization

Components:
- encoder: Symbol vocabulary encoder (Phase 1)
- memory_manager: GPU memory management (Phase 3)
- kernels: CUDA similarity kernels (Phase 3)
- matcher: Hybrid GPU+CPU matcher (Phase 3)
- sync_manager: Synchronization manager (Phase 3)
"""

__version__ = "0.3.0"  # Phase 3 implementation

from .encoder import SymbolVocabularyEncoder

# Phase 3 imports (check if CuPy available for graceful degradation)
try:
    from .memory_manager import GPUMemoryManager, CUPY_AVAILABLE
    from .kernels import CUDAPatternMatcher, test_determinism
    from .matcher import HybridGPUMatcher
    from .sync_manager import SyncManager
    from kato.config.gpu_settings import GPUConfig, DEFAULT_GPU_CONFIG

    # GPU is only available if CuPy is actually installed and working
    GPU_AVAILABLE = CUPY_AVAILABLE

except ImportError:
    # CuPy not available (e.g., macOS, no CUDA, etc.)
    # Create stub classes that raise informative errors
    GPU_AVAILABLE = False
    CUPY_AVAILABLE = False

    class GPUMemoryManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GPU acceleration unavailable - CuPy/CUDA required. "
                "Install CuPy or use CPU fallback."
            )

    class CUDAPatternMatcher:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GPU acceleration unavailable - CuPy/CUDA required. "
                "Install CuPy or use CPU fallback."
            )

    class HybridGPUMatcher:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GPU acceleration unavailable - CuPy/CUDA required. "
                "Install CuPy or use CPU fallback."
            )

    class SyncManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GPU acceleration unavailable - CuPy/CUDA required."
            )

    # Config is always available (doesn't require CuPy)
    from kato.config.gpu_settings import GPUConfig, DEFAULT_GPU_CONFIG

    def test_determinism():
        raise RuntimeError(
            "GPU testing unavailable - CuPy/CUDA required. "
            "Run on Linux system with NVIDIA GPU."
        )


__all__ = [
    # Phase 1
    "SymbolVocabularyEncoder",

    # Phase 3
    "GPUMemoryManager",
    "CUDAPatternMatcher",
    "HybridGPUMatcher",
    "SyncManager",
    "GPUConfig",
    "DEFAULT_GPU_CONFIG",
    "test_determinism",
    "GPU_AVAILABLE",
]
