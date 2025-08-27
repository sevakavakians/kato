"""
Vector Searches Module (Modernized)

This module now only contains utility functions for vector operations.
The main vector search functionality has been moved to vector_search_engine.py
"""

import logging
from os import environ

try:
    from numpy.linalg import norm
except ImportError:
    # Fallback if numpy is not properly installed
    def norm(x):
        return sum(i**2 for i in x) ** 0.5

logger = logging.getLogger('kato.searches.classification')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


def calculate_diff_lengths(data):
    """
    Calculate the length of the differences between current and all known vectors.
    
    Args:
        data: Tuple of (state, vec) where state and vec are vectors
    
    Returns:
        List containing [vec, norm(state - vec)]
    """
    state, vec = data
    return [vec, norm(state - vec)]


# For backward compatibility, import CVCSearcherModern as CVCSearcher
from kato.searches.vector_search_engine import CVCSearcherModern as CVCSearcher

__all__ = ['CVCSearcher', 'calculate_diff_lengths']