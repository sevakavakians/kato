"""
Fast pattern matching algorithms for KATO sequence matching.
Implements optimized deterministic algorithms for improved performance.
"""

import logging
from typing import List, Tuple, Dict, Set, Optional, Any
from collections import defaultdict
import hashlib
from os import environ

logger = logging.getLogger('kato.searches.fast_matcher')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))


class RollingHash:
    """
    Rabin-Karp rolling hash for fast sequence filtering.
    Deterministic hash function with fixed prime values.
    """
    
    def __init__(self, prime: int = 101, modulo: int = 2**31 - 1):
        """
        Initialize rolling hash with fixed parameters for determinism.
        
        Args:
            prime: Prime number for polynomial rolling hash
            modulo: Modulo value to prevent overflow
        """
        self.prime = prime
        self.modulo = modulo
        self._hash_cache = {}
    
    def compute_hash(self, sequence: List[str]) -> int:
        """
        Compute hash for a sequence of symbols.
        Deterministic - same sequence always produces same hash.
        
        Args:
            sequence: List of symbols to hash
            
        Returns:
            Integer hash value
        """
        # Check cache first
        seq_key = tuple(sequence)
        if seq_key in self._hash_cache:
            return self._hash_cache[seq_key]
        
        hash_value = 0
        for i, symbol in enumerate(sequence):
            # Use deterministic string hash
            symbol_hash = hash(symbol) & 0x7FFFFFFF  # Ensure positive
            hash_value = (hash_value * self.prime + symbol_hash) % self.modulo
        
        self._hash_cache[seq_key] = hash_value
        return hash_value
    
    def rolling_update(self, old_hash: int, old_symbol: str, 
                      new_symbol: str, window_size: int) -> int:
        """
        Update hash by removing old symbol and adding new one.
        O(1) operation for sliding window.
        
        Args:
            old_hash: Previous hash value
            old_symbol: Symbol being removed
            new_symbol: Symbol being added
            window_size: Size of the window
            
        Returns:
            Updated hash value
        """
        old_symbol_hash = hash(old_symbol) & 0x7FFFFFFF
        new_symbol_hash = hash(new_symbol) & 0x7FFFFFFF
        
        # Remove old symbol contribution
        old_contribution = (old_symbol_hash * pow(self.prime, window_size - 1, self.modulo)) % self.modulo
        hash_value = (old_hash - old_contribution + self.modulo) % self.modulo
        
        # Shift and add new symbol
        hash_value = (hash_value * self.prime + new_symbol_hash) % self.modulo
        
        return hash_value


class SuffixArray:
    """
    Suffix array for fast pattern searching in sequences.
    Provides O(n log n) construction and O(m log n) search.
    """
    
    def __init__(self, sequence: List[str]):
        """
        Build suffix array for the given sequence.
        
        Args:
            sequence: List of symbols to index
        """
        self.sequence = sequence
        self.n = len(sequence)
        self.suffix_array = self._build_suffix_array()
        self.lcp = self._build_lcp_array()
    
    def _build_suffix_array(self) -> List[int]:
        """
        Build suffix array using deterministic sorting.
        
        Returns:
            List of indices representing sorted suffixes
        """
        # Create tuples of (suffix, original_index)
        suffixes = []
        for i in range(self.n):
            suffix = tuple(self.sequence[i:])  # Use tuple for hashability
            suffixes.append((suffix, i))
        
        # Sort lexicographically (deterministic)
        suffixes.sort(key=lambda x: x[0])
        
        # Extract indices
        return [idx for _, idx in suffixes]
    
    def _build_lcp_array(self) -> List[int]:
        """
        Build Longest Common Prefix array for enhanced searching.
        
        Returns:
            LCP array
        """
        lcp = [0] * self.n
        rank = [0] * self.n
        
        # Build rank array (inverse of suffix array)
        for i, suffix_idx in enumerate(self.suffix_array):
            rank[suffix_idx] = i
        
        h = 0
        for i in range(self.n):
            if rank[i] > 0:
                j = self.suffix_array[rank[i] - 1]
                while i + h < self.n and j + h < self.n and \
                      self.sequence[i + h] == self.sequence[j + h]:
                    h += 1
                lcp[rank[i]] = h
                if h > 0:
                    h -= 1
        
        return lcp
    
    def search(self, pattern: List[str]) -> List[int]:
        """
        Search for pattern in the sequence using binary search.
        
        Args:
            pattern: Pattern to search for
            
        Returns:
            List of starting positions where pattern occurs
        """
        if not pattern:
            return []
        
        # Binary search for leftmost occurrence
        left = self._binary_search_left(pattern)
        if left == -1:
            return []
        
        # Binary search for rightmost occurrence
        right = self._binary_search_right(pattern)
        
        # Extract all occurrences
        positions = []
        for i in range(left, right + 1):
            positions.append(self.suffix_array[i])
        
        return sorted(positions)  # Return in sequence order
    
    def _binary_search_left(self, pattern: List[str]) -> int:
        """Find leftmost suffix that matches pattern."""
        left, right = 0, self.n - 1
        result = -1
        
        while left <= right:
            mid = (left + right) // 2
            suffix_start = self.suffix_array[mid]
            
            # Compare pattern with suffix
            comparison = self._compare_pattern(pattern, suffix_start)
            
            if comparison <= 0:
                if comparison == 0:
                    result = mid
                right = mid - 1
            else:
                left = mid + 1
        
        return result
    
    def _binary_search_right(self, pattern: List[str]) -> int:
        """Find rightmost suffix that matches pattern."""
        left, right = 0, self.n - 1
        result = -1
        
        while left <= right:
            mid = (left + right) // 2
            suffix_start = self.suffix_array[mid]
            
            # Compare pattern with suffix
            comparison = self._compare_pattern(pattern, suffix_start)
            
            if comparison >= 0:
                if comparison == 0:
                    result = mid
                left = mid + 1
            else:
                right = mid - 1
        
        return result
    
    def _compare_pattern(self, pattern: List[str], suffix_start: int) -> int:
        """
        Compare pattern with suffix starting at suffix_start.
        
        Returns:
            -1 if pattern < suffix, 0 if match, 1 if pattern > suffix
        """
        pattern_len = len(pattern)
        
        for i in range(pattern_len):
            if suffix_start + i >= self.n:
                return 1  # Pattern is longer than remaining suffix
            
            if pattern[i] < self.sequence[suffix_start + i]:
                return -1
            elif pattern[i] > self.sequence[suffix_start + i]:
                return 1
        
        return 0  # Pattern matches


class NGramIndex:
    """
    N-gram index for fast partial matching and similarity search.
    """
    
    def __init__(self, n: int = 3):
        """
        Initialize n-gram index.
        
        Args:
            n: Size of n-grams
        """
        self.n = n
        self.index = defaultdict(set)
        self.pattern_ngrams = {}
    
    def index_pattern(self, pattern_id: str, sequence: List[str]):
        """
        Index a pattern's sequence using n-grams.
        
        Args:
            pattern_id: Unique identifier for the pattern
            sequence: Flattened sequence of symbols
        """
        ngrams = self._extract_ngrams(sequence)
        self.pattern_ngrams[pattern_id] = ngrams
        
        for ngram in ngrams:
            self.index[ngram].add(pattern_id)
    
    def search(self, query: List[str], threshold: float = 0.5) -> List[Tuple[str, float]]:
        """
        Search for patterns similar to query using n-gram overlap.
        
        Args:
            query: Query sequence
            threshold: Minimum similarity threshold (0-1)
            
        Returns:
            List of (pattern_id, similarity) tuples
        """
        query_ngrams = self._extract_ngrams(query)
        if not query_ngrams:
            return []
        
        # Find candidate patterns
        candidates = defaultdict(int)
        for ngram in query_ngrams:
            for pattern_id in self.index.get(ngram, []):
                candidates[pattern_id] += 1
        
        # Calculate similarities
        results = []
        for pattern_id, overlap_count in candidates.items():
            pattern_ngrams = self.pattern_ngrams[pattern_id]
            
            # Jaccard similarity
            union_size = len(query_ngrams) + len(pattern_ngrams) - overlap_count
            similarity = overlap_count / union_size if union_size > 0 else 0
            
            if similarity >= threshold:
                results.append((pattern_id, similarity))
        
        # Sort by similarity (descending) and then by pattern_id (for determinism)
        results.sort(key=lambda x: (-x[1], x[0]))
        
        return results
    
    def _extract_ngrams(self, sequence: List[str]) -> Set[tuple]:
        """
        Extract n-grams from a sequence.
        
        Args:
            sequence: List of symbols
            
        Returns:
            Set of n-gram tuples
        """
        if len(sequence) < self.n:
            return {tuple(sequence)} if sequence else set()
        
        ngrams = set()
        for i in range(len(sequence) - self.n + 1):
            ngram = tuple(sequence[i:i + self.n])
            ngrams.add(ngram)
        
        return ngrams


class FastSequenceMatcher:
    """
    Main class combining multiple fast matching algorithms.
    Provides optimized pattern matching while maintaining determinism.
    """
    
    def __init__(self, use_rolling_hash: bool = True,
                 use_suffix_array: bool = False,
                 use_ngram_index: bool = True,
                 ngram_size: int = 3):
        """
        Initialize fast matcher with configurable algorithms.
        
        Args:
            use_rolling_hash: Enable Rabin-Karp rolling hash
            use_suffix_array: Enable suffix array (memory intensive)
            use_ngram_index: Enable n-gram indexing
            ngram_size: Size of n-grams for indexing
        """
        self.use_rolling_hash = use_rolling_hash
        self.use_suffix_array = use_suffix_array
        self.use_ngram_index = use_ngram_index
        
        self.rolling_hash = RollingHash() if use_rolling_hash else None
        self.ngram_index = NGramIndex(ngram_size) if use_ngram_index else None
        self.suffix_arrays = {}  # pattern_id -> SuffixArray
        self.pattern_hashes = {}  # pattern_id -> hash
        self.patterns = {}  # pattern_id -> sequence
        
        logger.info(f"FastSequenceMatcher initialized with: "
                   f"rolling_hash={use_rolling_hash}, "
                   f"suffix_array={use_suffix_array}, "
                   f"ngram_index={use_ngram_index}")
    
    def add_pattern(self, pattern_id: str, sequence: List[str]):
        """
        Add a pattern to the matcher's index.
        
        Args:
            pattern_id: Unique identifier for the pattern
            sequence: Flattened sequence of symbols
        """
        self.patterns[pattern_id] = sequence
        
        if self.use_rolling_hash:
            self.pattern_hashes[pattern_id] = self.rolling_hash.compute_hash(sequence)
        
        if self.use_suffix_array:
            self.suffix_arrays[pattern_id] = SuffixArray(sequence)
        
        if self.use_ngram_index:
            self.ngram_index.index_pattern(pattern_id, sequence)
    
    def find_matches(self, query: List[str], 
                    threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        Find patterns matching the query sequence.
        
        Args:
            query: Query sequence to match
            threshold: Minimum similarity threshold
            
        Returns:
            List of match dictionaries with pattern_id, similarity, and match info
        """
        matches = []
        
        # Use n-gram index for initial filtering
        if self.use_ngram_index:
            candidates = self.ngram_index.search(query, threshold)
            candidate_ids = {pattern_id for pattern_id, _ in candidates}
        else:
            candidate_ids = set(self.patterns.keys())
        
        # Check each candidate
        for pattern_id in candidate_ids:
            pattern_sequence = self.patterns[pattern_id]
            
            # Quick hash-based filtering
            if self.use_rolling_hash and len(query) == len(pattern_sequence):
                query_hash = self.rolling_hash.compute_hash(query)
                if query_hash != self.pattern_hashes[pattern_id]:
                    continue
            
            # Calculate detailed similarity
            similarity = self._calculate_similarity(query, pattern_sequence)
            
            if similarity >= threshold:
                matches.append({
                    'pattern_id': pattern_id,
                    'similarity': similarity,
                    'pattern_length': len(pattern_sequence),
                    'query_length': len(query)
                })
        
        # Sort for determinism
        matches.sort(key=lambda x: (-x['similarity'], x['pattern_id']))
        
        return matches
    
    def _calculate_similarity(self, seq1: List[str], seq2: List[str]) -> float:
        """
        Calculate similarity between two sequences.
        Uses simple ratio for now, can be enhanced with edit distance.
        
        Args:
            seq1: First sequence
            seq2: Second sequence
            
        Returns:
            Similarity score (0-1)
        """
        if not seq1 and not seq2:
            return 1.0
        if not seq1 or not seq2:
            return 0.0
        
        # Find common elements (order-independent for now)
        set1 = set(seq1)
        set2 = set(seq2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def clear(self):
        """Clear all indexed patterns."""
        self.patterns.clear()
        self.pattern_hashes.clear()
        self.suffix_arrays.clear()
        if self.ngram_index:
            self.ngram_index.index.clear()
            self.ngram_index.pattern_ngrams.clear()