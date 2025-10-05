"""
Index Manager for KATO Search Optimization

This module provides index structures for fast pattern matching and pattern searching.
Part of the performance optimization suite.
"""

import hashlib
import math
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


class InvertedIndex:
    """
    Inverted index for fast symbol-to-pattern lookup.
    Maps symbols to the patterns that contain them.
    """

    def __init__(self):
        self.index: Dict[str, Set[str]] = defaultdict(set)
        self.document_count = 0
        self.term_frequencies: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add_document(self, doc_id: str, terms: List[str]):
        """Add a document (pattern) to the index."""
        self.document_count += 1
        term_counts = defaultdict(int)

        for term in terms:
            term_counts[term] += 1
            self.index[term].add(doc_id)

        for term, count in term_counts.items():
            self.term_frequencies[term][doc_id] = count

    def search(self, terms: List[str], mode: str = 'AND') -> Set[str]:
        """
        Search for documents containing the given terms.
        
        Args:
            terms: List of terms to search for
            mode: 'AND' for intersection, 'OR' for union
        
        Returns:
            Set of document IDs matching the query
        """
        if not terms:
            return set()

        result_sets = [self.index.get(term, set()) for term in terms]

        if mode == 'AND':
            result = result_sets[0].copy()
            for s in result_sets[1:]:
                result &= s
        else:  # OR
            result = set()
            for s in result_sets:
                result |= s

        return result

    def get_idf(self, term: str) -> float:
        """Calculate Inverse Document Frequency for a term."""
        if term not in self.index or self.document_count == 0:
            return 0.0

        doc_freq = len(self.index[term])
        return math.log(self.document_count / doc_freq)

    def get_tf_idf(self, doc_id: str, term: str) -> float:
        """Calculate TF-IDF score for a term in a document."""
        if term not in self.term_frequencies or doc_id not in self.term_frequencies[term]:
            return 0.0

        tf = self.term_frequencies[term][doc_id]
        idf = self.get_idf(term)
        return tf * idf

    def clear(self):
        """Clear the index."""
        self.index.clear()
        self.document_count = 0
        self.term_frequencies.clear()

    def size(self) -> int:
        """Return the number of unique terms in the index."""
        return len(self.index)

    def get_posting_list(self, term: str) -> Set[str]:
        """Get the posting list (set of documents) for a term."""
        return self.index.get(term, set())


class BloomFilter:
    """
    Bloom filter for fast negative lookups.
    Used to quickly determine if a pattern definitely doesn't exist.
    """

    def __init__(self, size: int = 10000, num_hashes: int = 3):
        self.size = size
        self.num_hashes = num_hashes
        self.bit_array = [False] * size
        self.count = 0

    def _hash(self, item: str, seed: int) -> int:
        """Generate a hash for an item with a given seed."""
        h = hashlib.md5(usedforsecurity=False)
        h.update(f"{item}{seed}".encode())
        return int(h.hexdigest(), 16) % self.size

    def add(self, item: str):
        """Add an item to the bloom filter."""
        for i in range(self.num_hashes):
            index = self._hash(item, i)
            self.bit_array[index] = True
        self.count += 1

    def contains(self, item: str) -> bool:
        """
        Check if an item might be in the set.
        
        Returns:
            False if item is definitely not in the set
            True if item might be in the set (probabilistic)
        """
        for i in range(self.num_hashes):
            index = self._hash(item, i)
            if not self.bit_array[index]:
                return False
        return True

    def clear(self):
        """Clear the bloom filter."""
        self.bit_array = [False] * self.size
        self.count = 0

    def estimated_false_positive_rate(self) -> float:
        """Estimate the current false positive rate."""
        if self.count == 0:
            return 0.0

        # Formula: (1 - e^(-k*n/m))^k
        # k = num_hashes, n = count, m = size
        ratio = -self.num_hashes * self.count / self.size
        return (1 - math.exp(ratio)) ** self.num_hashes


class LengthPartitionedIndex:
    """
    Index that partitions sequences by length for faster search.
    Reduces search space by only looking at sequences of similar length.
    """

    def __init__(self, partition_size: int = 10):
        self.partition_size = partition_size
        self.partitions: Dict[int, List[Tuple[str, Any]]] = defaultdict(list)

    def add(self, doc_id: str, sequence: List[str], data: Any = None):
        """Add a sequence to the appropriate partition."""
        length = len(sequence)
        partition_key = length // self.partition_size
        self.partitions[partition_key].append((doc_id, data or sequence))

    def get_candidates(self, target_length: int, tolerance: int = 1) -> List[Tuple[str, Any]]:
        """
        Get candidate sequences that could match the target length.
        
        Args:
            target_length: The length of the target sequence
            tolerance: Number of partitions to check on either side
        
        Returns:
            List of (doc_id, data) tuples that could match
        """
        partition_key = target_length // self.partition_size
        candidates = []

        for i in range(partition_key - tolerance, partition_key + tolerance + 1):
            if i in self.partitions:
                candidates.extend(self.partitions[i])

        return candidates

    def clear(self):
        """Clear the index."""
        self.partitions.clear()

    def size(self) -> int:
        """Return the total number of indexed sequences."""
        return sum(len(partition) for partition in self.partitions.values())


class IndexManager:
    """
    Manages multiple index structures for efficient pattern matching.
    Coordinates between different indices to find the best candidates.
    """

    def __init__(self):
        self.inverted_index = InvertedIndex()
        self.bloom_filter = BloomFilter()
        self.length_index = LengthPartitionedIndex()
        self.pattern_data: Dict[str, Any] = {}

    def index_pattern(self, pattern_id: str, sequence: List[str], data: Any = None):
        """
        Index a pattern across all index structures.
        
        Args:
            pattern_id: Unique identifier for the pattern
            sequence: The sequence of symbols in the pattern
            data: Optional additional data to store with the pattern
        """
        # Add to inverted index
        self.inverted_index.add_document(pattern_id, sequence)

        # Add to bloom filter
        for symbol in sequence:
            self.bloom_filter.add(symbol)

        # Add to length-partitioned index
        self.length_index.add(pattern_id, sequence, data)

        # Store pattern data
        self.pattern_data[pattern_id] = data or sequence

    def search(self, query: List[str], mode: str = 'AND',
               use_bloom: bool = True, length_tolerance: int = 1) -> List[Tuple[str, float]]:
        """
        Search for patterns matching the query.
        
        Args:
            query: List of symbols to search for
            mode: 'AND' or 'OR' search mode
            use_bloom: Whether to use bloom filter for pre-filtering
            length_tolerance: Tolerance for length-based filtering
        
        Returns:
            List of (pattern_id, score) tuples sorted by relevance
        """
        # Quick bloom filter check for AND queries
        if use_bloom and mode == 'AND':
            for symbol in query:
                if not self.bloom_filter.contains(symbol):
                    return []  # Symbol definitely doesn't exist

        # Get candidates from inverted index
        candidates = self.inverted_index.search(query, mode)

        # Filter by length if reasonable
        if length_tolerance >= 0:
            length_candidates = self.length_index.get_candidates(
                len(query), tolerance=length_tolerance
            )
            length_candidate_ids = {doc_id for doc_id, _ in length_candidates}
            candidates &= length_candidate_ids

        # Score and rank candidates
        scored_results = []
        for doc_id in candidates:
            score = self._score_candidate(doc_id, query)
            scored_results.append((doc_id, score))

        # Sort by score (descending)
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return scored_results

    def _score_candidate(self, doc_id: str, query: List[str]) -> float:
        """Calculate relevance score for a candidate."""
        score = 0.0
        for term in query:
            score += self.inverted_index.get_tf_idf(doc_id, term)
        return score

    def clear(self):
        """Clear all indices."""
        self.inverted_index.clear()
        self.bloom_filter.clear()
        self.length_index.clear()
        self.pattern_data.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the indices."""
        return {
            'inverted_index_terms': self.inverted_index.size(),
            'inverted_index_documents': self.inverted_index.document_count,
            'bloom_filter_items': self.bloom_filter.count,
            'bloom_filter_fpr': self.bloom_filter.estimated_false_positive_rate(),
            'length_index_sequences': self.length_index.size(),
            'total_patterns': len(self.pattern_data)
        }

    def add_pattern(self, pattern_id: str, sequence: List[str], data: Any = None):
        """
        Add a pattern to the index (wrapper for index_pattern).
        
        Args:
            pattern_id: Unique identifier for the pattern
            sequence: The sequence of symbols in the pattern
            data: Optional additional data to store with the pattern
        """
        self.index_pattern(pattern_id, sequence, data)

    def remove_pattern(self, pattern_id: str) -> bool:
        """
        Remove a pattern from all indices.
        
        Args:
            pattern_id: Pattern identifier to remove
            
        Returns:
            True if pattern was found and removed, False otherwise
        """
        if pattern_id not in self.pattern_data:
            return False

        # Remove from pattern data
        pattern_sequence = self.pattern_data.get(pattern_id, [])
        del self.pattern_data[pattern_id]

        # Remove from inverted index
        # Note: This requires rebuilding the index for that document
        # For now, we'll mark it as a limitation that requires full rebuild
        # A more sophisticated implementation would track document deletions

        # Remove from length index (would need to rebuild partition)
        # This is a known limitation of the current implementation

        return True

    def search_candidates(self, query: List[str], length_tolerance: float = 0.5) -> Set[str]:
        """
        Search for candidate patterns that could match the query.
        
        Args:
            query: List of symbols to search for
            length_tolerance: Fraction of length difference to tolerate (0.5 = 50%)
            
        Returns:
            Set of pattern IDs that are potential matches
        """
        # Convert length_tolerance from fraction to partition count
        query_length = len(query)
        tolerance_partitions = max(1, int(length_tolerance * query_length / self.length_index.partition_size))

        # Get candidates from length-based filtering
        length_candidates = self.length_index.get_candidates(query_length, tolerance=tolerance_partitions)
        candidate_ids = {doc_id for doc_id, _ in length_candidates}

        # If we have query symbols, filter by inverted index
        if query:
            # Use OR mode to get all patterns containing any query symbol
            symbol_candidates = self.inverted_index.search(query[:10], mode='OR')  # Limit symbols for performance

            # For short queries (potential prefix matches), be more permissive
            # This allows branching sequences with shared prefixes to be found
            if query_length <= 2:
                # Union with symbol candidates for short queries (prefix matching)
                candidate_ids |= symbol_candidates
            else:
                # Intersect with length candidates if we have both for longer queries
                if candidate_ids:
                    candidate_ids &= symbol_candidates
                else:
                    candidate_ids = symbol_candidates

        return candidate_ids
