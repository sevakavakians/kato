"""
Hash Helper Utilities for KATO Tests
Provides utilities for verifying deterministic hashing of patterns and vectors.
"""

import hashlib
import json
from typing import Any, Dict, List


def calculate_pattern_hash(sequence: List[Any]) -> str:
    """
    Calculate the SHA1 hash for a pattern/sequence.
    
    Args:
        sequence: List of observations that form the sequence
        
    Returns:
        The SHA1 hash of the sequence (without PTRN| prefix)
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
        The SHA1 hash of the vector (without VCTR| prefix)
    """
    # Convert vector to a canonical string representation
    vector_str = json.dumps(vector)
    return hashlib.sha1(vector_str.encode()).hexdigest()


def format_pattern_name(sequence: List[Any]) -> str:
    """
    Format a pattern name with the PTRN| prefix and hash.
    
    Args:
        sequence: The sequence to hash
        
    Returns:
        Formatted pattern name like 'PTRN|abc123...'
    """
    hash_value = calculate_pattern_hash(sequence)
    return f"PTRN|{hash_value}"


def format_vector_name(vector: List[float]) -> str:
    """
    Format a vector name with the VCTR| prefix and hash.
    
    Args:
        vector: The vector to hash
        
    Returns:
        Formatted vector name like 'VCTR|abc123...'
    """
    hash_value = calculate_vector_hash(vector)
    return f"VCTR|{hash_value}"


def verify_pattern_name(name: str, expected_sequence: List[Any]) -> bool:
    """
    Verify that a pattern name matches the expected format and hash.
    
    Args:
        name: The pattern name to verify
        expected_sequence: The sequence that should produce this hash
        
    Returns:
        True if the name is correctly formatted and matches the expected hash
    """
    if not name.startswith("PTRN|"):
        return False

    expected_name = format_pattern_name(expected_sequence)
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
    if not name.startswith("VCTR|"):
        return False

    expected_name = format_vector_name(expected_vector)
    return name == expected_name


def extract_hash_from_name(name: str) -> str:
    """
    Extract the hash portion from a PTRN| or VCTR| prefixed name.
    
    Args:
        name: The prefixed name
        
    Returns:
        The hash portion of the name, or empty string if invalid format
    """
    if name.startswith("PTRN|"):
        return name[5:]
    elif name.startswith("VCTR|"):
        return name[7:]
    return ""


# All model_name references have been renamed to pattern_name


def verify_hash_consistency(names: List[str], sequences: List[List[Any]]) -> Dict[str, bool]:
    """
    Verify that a list of pattern names consistently hash to the same values.
    
    Args:
        names: List of pattern names to verify
        sequences: Corresponding sequences for each name
        
    Returns:
        Dictionary mapping each name to whether it's consistent
    """
    results = {}
    hash_map = {}

    for name, sequence in zip(names, sequences):
        seq_str = json.dumps(sequence, sort_keys=True)
        expected_hash = calculate_pattern_hash(sequence)
        actual_hash = extract_hash_from_name(name)

        if seq_str in hash_map:
            # We've seen this sequence before
            results[name] = (hash_map[seq_str] == actual_hash)
        else:
            # First time seeing this sequence
            hash_map[seq_str] = actual_hash
            results[name] = (expected_hash == actual_hash)

    return results
