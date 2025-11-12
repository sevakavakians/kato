"""
Pattern filtering framework for billion-scale knowledge base queries.

This module provides the filter pipeline infrastructure for KATO's hybrid
ClickHouse + Redis architecture.
"""

from kato.filters.base import PatternFilter
from kato.filters.executor import FilterPipelineExecutor
from kato.filters.length_filter import LengthFilter
from kato.filters.jaccard_filter import JaccardFilter
from kato.filters.minhash_filter import MinHashFilter
from kato.filters.bloom_filter_stage import BloomFilterStage
from kato.filters.rapidfuzz_filter import RapidFuzzFilter

# Register filters
FilterPipelineExecutor.register_filter('length', LengthFilter)
FilterPipelineExecutor.register_filter('jaccard', JaccardFilter)
FilterPipelineExecutor.register_filter('minhash', MinHashFilter)
FilterPipelineExecutor.register_filter('bloom', BloomFilterStage)
FilterPipelineExecutor.register_filter('rapidfuzz', RapidFuzzFilter)

__all__ = [
    'PatternFilter',
    'FilterPipelineExecutor',
    'LengthFilter',
    'JaccardFilter',
    'MinHashFilter',
    'BloomFilterStage',
    'RapidFuzzFilter'
]
