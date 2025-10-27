"""
GPU acceleration module for KATO pattern matching.

This module provides GPU-accelerated pattern matching using CUDA/CuPy.
It includes:
- Symbol vocabulary encoder (string to integer mapping)
- GPU memory management
- CUDA kernels for similarity computation
- Hybrid GPU/CPU matcher for optimal performance

Phase 1 (Current): Foundation & Profiling
- SymbolVocabularyEncoder: String ↔ integer mapping with MongoDB persistence

Future Phases:
- Phase 2: CPU optimization with RapidFuzz
- Phase 3: GPU core implementation (kernels, memory manager, matcher)
- Phase 4: Learning integration and sync mechanisms
- Phase 5: Production hardening (monitoring, error handling)
"""

__version__ = "0.1.0"

from .encoder import SymbolVocabularyEncoder

__all__ = [
    "SymbolVocabularyEncoder",
]
