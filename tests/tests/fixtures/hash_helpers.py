"""
Hash Helper Utilities for KATO Tests
Provides utilities for verifying deterministic hashing of models and vectors.
"""

import hashlib
import json
from typing import List, Dict, Any, Tuple


def calculate_model_hash(sequence: List[Any]) -> str:
    """
    Calculate the SHA1 hash for a model/sequence.
    
    Args:
        sequence: List of observations that form the sequence
        
    Returns:
        The SHA1 hash of the sequence (without MODEL| prefix)
    """
    # Convert sequence to a canonical string representation
    sequence_str = json.dumps(sequence, sort_keys=True)
    return hashlib.sha1(sequence_str.encode()).hexdigest()


def calculate_vector_hash(vector: List[float]) -> str:
    """
    Calculate the SHA1 hash for a vector.
    
    Args:
        vector: List of float values
        
    Returns:
        The SHA1 hash of the vector (without VECTOR| prefix)
    """
    # Convert vector to a canonical string representation
    vector_str = json.dumps(vector)
    return hashlib.sha1(vector_str.encode()).hexdigest()


def format_model_name(sequence: List[Any]) -> str:
    """
    Format a model name with the MODEL| prefix and hash.
    
    Args:
        sequence: The sequence to hash
        
    Returns:
        Formatted model name like 'MODEL|abc123...'
    """
    hash_value = calculate_model_hash(sequence)
    return f"MODEL|{hash_value}"


def format_vector_name(vector: List[float]) -> str:
    """
    Format a vector name with the VECTOR| prefix and hash.
    
    Args:
        vector: The vector to hash
        
    Returns:
        Formatted vector name like 'VECTOR|abc123...'
    """
    hash_value = calculate_vector_hash(vector)
    return f"VECTOR|{hash_value}"


def verify_model_name(name: str, expected_sequence: List[Any]) -> bool:
    """
    Verify that a model name matches the expected format and hash.
    
    Args:
        name: The model name to verify
        expected_sequence: The sequence that should produce this hash
        
    Returns:
        True if the name is correctly formatted and matches the expected hash
    """
    if not name.startswith("MODEL|"):
        return False
    
    expected_name = format_model_name(expected_sequence)
    return name == expected_name


def verify_vector_name(name: str, expected_vector: List[float]) -> bool:
    """
    Verify that a vector name matches the expected format and hash.
    
    Args:
        name: The vector name to verify
        expected_vector: The vector that should produce this hash
        
    Returns:
        True if the name is correctly formatted and matches the expected hash
    """
    if not name.startswith("VECTOR|"):
        return False
    
    expected_name = format_vector_name(expected_vector)
    return name == expected_name


def extract_hash_from_name(name: str) -> str:
    """
    Extract the hash portion from a MODEL| or VECTOR| prefixed name.
    
    Args:
        name: The prefixed name
        
    Returns:
        The hash portion of the name, or empty string if invalid format
    """
    if name.startswith("MODEL|"):
        return name[6:]
    elif name.startswith("VECTOR|"):
        return name[7:]
    return ""


def verify_hash_consistency(names: List[str], sequences: List[List[Any]]) -> Dict[str, bool]:
    """
    Verify that a list of model names consistently hash to the same values.
    
    Args:
        names: List of model names to verify
        sequences: Corresponding sequences for each name
        
    Returns:
        Dictionary mapping each name to whether it's consistent
    """
    results = {}
    hash_map = {}
    
    for name, sequence in zip(names, sequences):
        seq_str = json.dumps(sequence, sort_keys=True)
        expected_hash = calculate_model_hash(sequence)
        actual_hash = extract_hash_from_name(name)
        
        if seq_str in hash_map:
            # We've seen this sequence before
            results[name] = (hash_map[seq_str] == actual_hash)
        else:
            # First time seeing this sequence
            hash_map[seq_str] = actual_hash
            results[name] = (expected_hash == actual_hash)
    
    return results