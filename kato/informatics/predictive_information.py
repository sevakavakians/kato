"""
Predictive Information (Excess Entropy) calculations for KATO.

This module implements ensemble-based predictive information calculations
for ranking predictions based on their statistical relationships.
"""

import logging
from typing import List, Dict, Any, Tuple
import hashlib
import json

logger = logging.getLogger('kato.informatics.predictive_information')


def hash_future(future: List[List[str]]) -> str:
    """
    Create a deterministic hash for a future segment.
    
    Args:
        future: List of events representing the future
        
    Returns:
        SHA1 hash of the future for efficient comparison
    """
    # Sort symbols within each event for consistency
    normalized = [sorted(event) for event in future]
    # Convert to JSON for deterministic string representation
    future_str = json.dumps(normalized, sort_keys=True)
    return hashlib.sha1(future_str.encode()).hexdigest()


def calculate_future_aggregates(predictions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate predictions by unique futures and calculate their collective potentials.
    
    Args:
        predictions: List of prediction dictionaries from pattern matching
        
    Returns:
        Dictionary mapping future hashes to aggregate information
    """
    future_aggregates = {}
    
    for pattern in predictions:
        future = pattern.get('future', [])
        if not future:
            continue
            
        future_key = hash_future(future)
        
        if future_key not in future_aggregates:
            future_aggregates[future_key] = {
                'future': future,
                'total_weighted_frequency': 0.0,
                'pattern_count': 0,
                'patterns': []
            }
        
        # Weight frequency by similarity (how well pattern matches observation)
        similarity = pattern.get('similarity', 1.0)
        frequency = pattern.get('frequency', 1)
        weighted_freq = frequency * similarity
        
        future_aggregates[future_key]['total_weighted_frequency'] += weighted_freq
        future_aggregates[future_key]['pattern_count'] += 1
        future_aggregates[future_key]['patterns'].append(pattern.get('name', 'unknown'))
    
    # Calculate aggregate potentials
    total_weighted = sum(fa['total_weighted_frequency'] for fa in future_aggregates.values())
    
    if total_weighted > 0:
        for fa in future_aggregates.values():
            fa['aggregate_potential'] = fa['total_weighted_frequency'] / total_weighted
    else:
        # No valid futures found
        for fa in future_aggregates.values():
            fa['aggregate_potential'] = 0.0
    
    return future_aggregates


def calculate_ensemble_predictive_information(
    predictions: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Calculate predictive information for each prediction in an ensemble
    using dual-level scoring (pattern-level and future-level).
    
    Args:
        predictions: List of prediction dictionaries from pattern matching
        
    Returns:
        Tuple of (updated predictions with PI and potential, future potentials list)
    """
    if not predictions:
        return predictions, []
    
    # Calculate ensemble-wide statistics
    sum_ensemble_frequencies = sum(p.get('frequency', 1) for p in predictions)
    
    if sum_ensemble_frequencies == 0:
        # No valid frequencies, return as-is
        for p in predictions:
            p['predictive_information'] = 0.0
            p['potential'] = 0.0
        return predictions, []
    
    # Phase 1: Calculate pattern probabilities
    for pattern in predictions:
        frequency = pattern.get('frequency', 1)
        pattern['pattern_probability'] = frequency / sum_ensemble_frequencies
        pattern['weighted_strength'] = pattern.get('similarity', 1.0) * pattern['pattern_probability']
    
    # Phase 2: Aggregate by futures
    future_aggregates = calculate_future_aggregates(predictions)
    
    # Phase 3: Calculate predictive information and potential for each pattern
    for pattern in predictions:
        future = pattern.get('future', [])
        if not future:
            pattern['predictive_information'] = 0.0
            pattern['potential'] = 0.0
            continue
        
        future_key = hash_future(future)
        future_aggregate = future_aggregates.get(future_key, {})
        future_potential = future_aggregate.get('aggregate_potential', 0.0)
        
        # Predictive information: How much this specific pattern contributes
        # to the prediction of its future relative to other patterns
        if future_potential > 0:
            # Pattern's contribution to its future's prediction
            pattern['predictive_information'] = pattern['weighted_strength'] / future_potential
        else:
            pattern['predictive_information'] = 0.0
        
        # Final potential: similarity * predictive_information
        # As requested: new simplified formula for potential
        pattern['potential'] = pattern.get('similarity', 1.0) * pattern['predictive_information']
    
    # Prepare future potentials for response
    future_potentials = [
        {
            'future': fa['future'],
            'aggregate_potential': fa['aggregate_potential'],
            'supporting_patterns': fa['pattern_count'],
            'total_weighted_frequency': fa['total_weighted_frequency']
        }
        for fa in sorted(
            future_aggregates.values(), 
            key=lambda x: x['aggregate_potential'], 
            reverse=True
        )
    ]
    
    return predictions, future_potentials