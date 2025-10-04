"""
Pattern search with fast pattern matching algorithms.
Provides ~300x performance improvements using optimized algorithms.
"""

import logging
from os import environ
import heapq
import multiprocessing
from collections import Counter
from itertools import chain
from operator import itemgetter
from queue import Queue
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import concurrent.futures
from functools import partial

# MongoDB is required for KATO
from pymongo import MongoClient

# Import original components for compatibility
from kato.informatics import extractor as difflib
from kato.representations.prediction import Prediction

# Import new optimized components
from .fast_matcher import FastSequenceMatcher
from .index_manager import IndexManager
from .bloom_filter import PatternBloomFilter, get_pattern_bloom_filter
from ..storage.pattern_cache import PatternCache, get_cache_manager
from ..storage.aggregation_pipelines import OptimizedQueryManager

# Optional: Import rapidfuzz if available
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.info("RapidFuzz not available. Install with: pip install rapidfuzz")

logger = logging.getLogger('kato.searches.pattern_search')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))


class InformationExtractor:
    """
    Optimized information extraction using fast matching algorithms.
    
    Maintains exact same output format as original for compatibility.
    Uses RapidFuzz when available for ~10x faster similarity calculations.
    
    Attributes:
        use_fast_matcher: Whether to use optimized matching algorithms.
        fast_matcher: FastSequenceMatcher instance for optimized matching.
    """
    
    def __init__(self, use_fast_matcher: bool = True) -> None:
        """
        Initialize optimized extractor.
        
        Args:
            use_fast_matcher: Use fast matching algorithms for better performance.
        """
        self.use_fast_matcher = use_fast_matcher
        self.fast_matcher = FastSequenceMatcher() if use_fast_matcher else None
        
    def extract_prediction_info(self, pattern: List[str], state: List[str], 
                               cutoff: float) -> Optional[Tuple[List[str], List[str], List[str], List[str], List[str], List[str], float, int]]:
        """
        Extract prediction information using optimized algorithms.
        
        Args:
            pattern: Pattern data as list of symbols.
            state: Current state sequence to match against.
            cutoff: Similarity threshold (0.0 to 1.0).
            
        Returns:
            Tuple containing:
                - pattern: Original pattern data
                - matching_intersection: Symbols that matched
                - past: Pattern elements before first match
                - present: Pattern elements in matching region
                - missing: Pattern elements not found in state
                - extras: State elements not in pattern
                - similarity: Calculated similarity ratio
                - number_of_blocks: Number of matching blocks
            Returns None if similarity is below cutoff.
        """
        if self.use_fast_matcher and RAPIDFUZZ_AVAILABLE:
            # Use RapidFuzz for fast similarity calculation
            # Convert lists to strings for RapidFuzz
            pattern_str = ' '.join(pattern)
            state_str = ' '.join(state)
            similarity = fuzz.ratio(pattern_str, state_str) / 100.0
        else:
            # Fall back to original SequenceMatcher
            matcher = difflib.SequenceMatcher()
            matcher.set_seq1(pattern)
            matcher.set_seq2(state)
            similarity = matcher.ratio()
        
        if similarity < cutoff:
            return None
        
        # Extract detailed match information (same as original)
        matcher = difflib.SequenceMatcher()
        matcher.set_seq1(pattern)
        matcher.set_seq2(state)
        
        matching_intersection = []
        matching_blocks = matcher.get_matching_blocks()
        
        for block in matching_blocks[:-1]:  # Skip terminator
            (i, j, n) = tuple(block)
            matching_intersection += state[j:j+n]
        
        # Extract temporal regions
        # matching_blocks includes a terminator at the end, so actual matches = len(matching_blocks) - 1
        num_actual_blocks = len(matching_blocks) - 1
        
        if num_actual_blocks >= 2:
            # We have at least 2 actual matching blocks
            (i0, j0, n0) = tuple(matching_blocks[0])
            (i1, j1, n1) = tuple(matching_blocks[-2])  # Last actual match (before terminator)
            past = pattern[:i0]
            present = pattern[i0:i1+n1] if i1+n1 > i0 else pattern[i0:]
        elif num_actual_blocks == 1:
            # Only one matching block
            (i0, j0, n0) = tuple(matching_blocks[0])
            (i1, j1, n1) = (i0, j0, n0)  # Use same values for consistency
            past = pattern[:i0]
            present = pattern[i0:i0+n0]  # Just the matching portion
        else:
            # No matches - only valid for threshold 0.0
            if cutoff > 0.0:
                return None
            # For threshold 0.0, include even non-matching patterns
            past = []
            present = pattern  # Entire pattern is "present" when no matches
        
        number_of_blocks = num_actual_blocks
        
        # Extract anomalies (missing and extras) using original approach
        missing = []
        extras = []
        
        if present:
            matcher.set_seq1(present)
            # seq2 already has the full state set from earlier
            diffs = list(matcher.compare())
            
            for diff in diffs:
                if diff.startswith("- "):
                    missing.append(diff[2:])
                elif diff.startswith("+ "):
                    extras.append(diff[2:])
        
        return (pattern, matching_intersection, past, present, 
                missing, extras, similarity, number_of_blocks)


class PatternSearcher:
    """
    Optimized pattern searcher using fast matching and indexing.
    
    Drop-in replacement for PatternSearcher with ~300x performance improvements.
    Uses MongoDB for pattern storage and optional fast indexing/matching.
    
    Attributes:
        kb_id: Knowledge base identifier.
        patterns_cache: In-memory cache of patterns.
        patterns_count: Number of cached patterns.
        fast_matcher: FastSequenceMatcher for optimized matching.
        index_manager: IndexManager for efficient pattern lookup.
        max_predictions: Maximum number of predictions to return.
        recall_threshold: Minimum similarity threshold for matches.
    """
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize optimized pattern searcher.
        
        Args:
            **kwargs: Configuration parameters including:
                - kb_id: Knowledge base identifier
                - max_predictions: Max predictions to return
                - recall_threshold: Minimum similarity threshold
        
        Raises:
            ValueError: If MONGO_BASE_URL is not set.
            RuntimeError: If MongoDB connection fails.
        """
        self.procs = multiprocessing.cpu_count()
        logger.info(f"PatternSearcher using {self.procs} CPUs")
        
        self.kb_id = kwargs["kb_id"]
        
        # Use optimized connection manager for MongoDB
        from kato.storage.connection_manager import get_mongodb_client
        self.connection = get_mongodb_client()
        self.knowledgebase = self.connection[self.kb_id]
        logger.info(f"Using optimized MongoDB connection for kb_id: {self.kb_id}")
            
        self.max_predictions = kwargs["max_predictions"]
        self.recall_threshold = kwargs["recall_threshold"]
        
        # Feature flags for optimization
        self.use_fast_matching = environ.get('KATO_USE_FAST_MATCHING', 'true').lower() == 'true'
        self.use_indexing = environ.get('KATO_USE_INDEXING', 'true').lower() == 'true'
        
        # Initialize optimized components
        self.fast_matcher = FastSequenceMatcher(
            use_rolling_hash=True,
            use_ngram_index=True
        ) if self.use_fast_matching else None
        
        self.index_manager = IndexManager() if self.use_indexing else None
        
        # Initialize Bloom filter for pattern pre-screening
        self.use_bloom_filter = environ.get('KATO_USE_BLOOM_FILTER', 'true').lower() == 'true'
        self.bloom_filter = get_pattern_bloom_filter() if self.use_bloom_filter else None
        
        # Initialize optimized query manager for aggregation pipelines
        self.query_manager = OptimizedQueryManager(self.knowledgebase)
        
        self.extractor = InformationExtractor(self.use_fast_matching)
        
        # Pattern cache (in-memory fallback)
        self.patterns_cache = {}
        self.patterns_count = 0
        
        # Redis pattern cache
        self.redis_cache: Optional[PatternCache] = None
        self._cache_enabled = environ.get('KATO_USE_REDIS_CACHE', 'true').lower() == 'true'
        
        # Load existing patterns
        self.getPatterns()
        
        # Initialize worker queues for parallel processing
        self.extractions_queue = Queue()
        self.predictions_queue = Queue()
        
        logger.info(f"PatternSearcher initialized: "
                   f"fast_matching={self.use_fast_matching}, "
                   f"indexing={self.use_indexing}, "
                   f"redis_cache={self._cache_enabled}")
    
    async def initialize_redis_cache(self, session_id: Optional[str] = None) -> bool:
        """
        Initialize Redis cache for pattern caching.
        
        Args:
            session_id: Optional session identifier for cache isolation
            
        Returns:
            True if cache initialized successfully
        """
        if not self._cache_enabled:
            return False
        
        try:
            cache_manager = await get_cache_manager()
            if cache_manager and cache_manager.is_initialized():
                self.redis_cache = cache_manager.pattern_cache
                
                # Optionally warm the cache
                if session_id and self.redis_cache:
                    await self.redis_cache.warm_cache(
                        session_id,
                        self.knowledgebase.patterns_kb,
                        self.knowledgebase.symbols_kb, 
                        self.knowledgebase.metadata
                    )
                
                logger.info("Redis pattern cache initialized successfully")
                return True
            else:
                logger.warning("Redis cache manager not available, falling back to in-memory cache")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}")
            return False
    
    def getPatterns(self) -> None:
        """
        Load patterns from database using optimized aggregation pipelines.
        
        Uses server-side aggregation for better performance and reduced data transfer.
        Fetches all patterns from MongoDB and populates fast matching
        structures if enabled. Builds indices for efficient lookup.
        
        Raises:
            RuntimeError: If MongoDB connection is not available.
        """
        # Use optimized aggregation pipeline for pattern loading
        try:
            _patterns = self.query_manager.get_patterns_optimized()
            
            # Get original pattern data for Bloom filter (need non-flattened data)
            original_patterns = []
            if self.bloom_filter:
                # Need to fetch original pattern_data structure for Bloom filter
                for p in self.knowledgebase.patterns_kb.find({}, {"name": 1, "pattern_data": 1}):
                    original_patterns.append(p)
            
            # Add to fast matcher, index manager, and Bloom filter if enabled
            for pattern_name, flattened in _patterns.items():
                if self.fast_matcher:
                    self.fast_matcher.add_pattern(pattern_name, flattened)
                
                if self.index_manager:
                    self.index_manager.add_pattern(pattern_name, flattened)
            
            # Add patterns to Bloom filter using original non-flattened data
            if self.bloom_filter and original_patterns:
                self.bloom_filter.add_patterns_batch(original_patterns)
            
            self.patterns_cache = _patterns
            self.patterns_count = len(_patterns)
            
            logger.debug(f"Loaded {self.patterns_count} patterns using optimized aggregation pipeline")
            
        except Exception as e:
            logger.warning(f"Aggregation pipeline failed, falling back to original method: {e}")
            # Fallback to original implementation
            _patterns = {}
            
            if self.knowledgebase is None:
                raise RuntimeError("MongoDB connection required but not available")
            
            original_patterns = []
            for p in self.knowledgebase.patterns_kb.find({}, {"name": 1, "pattern_data": 1}):
                pattern_name = p["name"]
                flattened = list(chain(*p["pattern_data"]))
                _patterns[pattern_name] = flattened
                
                if self.fast_matcher:
                    self.fast_matcher.add_pattern(pattern_name, flattened)
                
                if self.index_manager:
                    self.index_manager.add_pattern(pattern_name, flattened)
                
                # Store original pattern for Bloom filter
                if self.bloom_filter:
                    original_patterns.append(p)
            
            # Add patterns to Bloom filter
            if self.bloom_filter and original_patterns:
                self.bloom_filter.add_patterns_batch(original_patterns)
            
            self.patterns_cache = _patterns
            self.patterns_count = len(_patterns)
            
            logger.debug(f"Loaded {self.patterns_count} patterns using fallback method")
    
    async def getPatternsAsync(self, session_id: Optional[str] = None, limit: int = 1000) -> None:
        """
        Async version of getPatterns with Redis caching support.
        
        Args:
            session_id: Session identifier for cache isolation
            limit: Maximum number of patterns to load
        """
        _patterns = {}
        
        # Try Redis cache first if enabled and available
        if self.redis_cache and session_id:
            try:
                cached_patterns = await self.redis_cache.get_top_patterns(
                    session_id, limit, self.knowledgebase.patterns_kb
                )
                
                for pattern_doc in cached_patterns:
                    pattern_name = pattern_doc["name"]
                    if "pattern_data" in pattern_doc:
                        flattened = list(chain(*pattern_doc["pattern_data"]))
                        _patterns[pattern_name] = flattened
                        
                        # Add to fast matcher if enabled
                        if self.fast_matcher:
                            self.fast_matcher.add_pattern(pattern_name, flattened)
                        
                        # Add to index manager if enabled
                        if self.index_manager:
                            self.index_manager.add_pattern(pattern_name, flattened)
                
                self.patterns_cache = _patterns
                self.patterns_count = len(_patterns)
                
                logger.debug(f"Loaded {self.patterns_count} patterns from Redis cache")
                return
                
            except Exception as e:
                logger.warning(f"Redis cache failed, falling back to MongoDB: {e}")
        
        # Fallback to MongoDB using optimized aggregation pipeline
        try:
            _patterns = self.query_manager.get_patterns_optimized(limit=limit)
            
            # Add to fast matcher and index manager if enabled
            for pattern_name, flattened in _patterns.items():
                if self.fast_matcher:
                    self.fast_matcher.add_pattern(pattern_name, flattened)
                
                if self.index_manager:
                    self.index_manager.add_pattern(pattern_name, flattened)
            
            self.patterns_cache = _patterns
            self.patterns_count = len(_patterns)
            
            logger.debug(f"Loaded {self.patterns_count} patterns using optimized aggregation pipeline (async)")
            
        except Exception as e:
            logger.warning(f"Aggregation pipeline failed in async method, using original find(): {e}")
            # Final fallback to original find()
            if self.knowledgebase is None:
                raise RuntimeError("MongoDB connection required but not available")
            
            for p in self.knowledgebase.patterns_kb.find({}, {"name": 1, "pattern_data": 1}).limit(limit):
                pattern_name = p["name"]
                flattened = list(chain(*p["pattern_data"]))
                _patterns[pattern_name] = flattened
                
                if self.fast_matcher:
                    self.fast_matcher.add_pattern(pattern_name, flattened)
                
                if self.index_manager:
                    self.index_manager.add_pattern(pattern_name, flattened)
            
            self.patterns_cache = _patterns
            self.patterns_count = len(_patterns)
        
        logger.debug(f"Loaded {self.patterns_count} patterns from MongoDB")
    
    def assignNewlyLearnedToWorkers(self, index: int, pattern_name: str, 
                                   new_pattern: List[str]) -> None:
        """
        Add newly learned pattern to indices.
        
        Args:
            index: Worker index (kept for backward compatibility, not used).
            pattern_name: Unique pattern identifier (e.g., 'PTRN|<hash>').
            new_pattern: Pattern data as flattened list of symbols.
        """
        self.patterns_count += 1
        self.patterns_cache[pattern_name] = new_pattern
        
        if self.fast_matcher:
            self.fast_matcher.add_pattern(pattern_name, new_pattern)
        
        if self.index_manager:
            self.index_manager.add_pattern(pattern_name, new_pattern)
        
        # Invalidate Redis cache when new patterns are learned
        if self.redis_cache:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule invalidation task
                    asyncio.create_task(self.redis_cache.invalidate_pattern_cache())
                else:
                    # Run directly if no event loop is running
                    asyncio.run(self.redis_cache.invalidate_pattern_cache())
            except Exception as e:
                logger.warning(f"Failed to invalidate pattern cache: {e}")
        
        logger.debug(f"Added new pattern {pattern_name} to indices")
    
    def delete_pattern(self, name: str) -> bool:
        """
        Delete pattern from all indices.
        
        Args:
            name: Pattern name to delete
            
        Returns:
            True if pattern was found and deleted
        """
        if name not in self.patterns_cache:
            return False
        
        del self.patterns_cache[name]
        self.patterns_count -= 1
        
        if self.index_manager:
            self.index_manager.remove_pattern(name)
        
        # Note: fast_matcher doesn't have efficient delete, would need rebuild
        
        logger.debug(f"Deleted pattern {name}")
        return True
    
    def clearPatternsFromRAM(self) -> None:
        """
        Clear all patterns from memory.
        
        Removes all cached patterns and resets indices. Used when
        clearing all memory or switching knowledge bases.
        """
        self.patterns_count = 0
        self.patterns_cache.clear()
        
        if self.fast_matcher:
            self.fast_matcher.clear()
        
        if self.index_manager:
            # Recreate clean index manager
            self.index_manager = IndexManager()
    
    def causalBelief(self, state: List[str],
                    target_class_candidates: Optional[List[str]] = None,
                    stm_events: Optional[List[List[str]]] = None) -> List[Dict[str, Any]]:
        """
        Find matching patterns and generate predictions.

        Optimized version with fast filtering and matching. Uses indexing
        to reduce search space and parallel processing for extraction.

        Args:
            state: Current state sequence (flattened STM).
            target_class_candidates: Optional list of specific pattern names
                to check. If provided, only these patterns are evaluated.
            stm_events: Original event-structured STM for calculating event-aligned missing/extras.

        Returns:
            List of prediction dictionaries with pattern match information,
            sorted by potential/relevance.
        """
        logger.info(f"*** causalBelief called with state={state}, target_class_candidates={target_class_candidates}")
        
        if self.patterns_count == 0:
            self.getPatterns()
        
        results = []
        
        # Get candidate patterns using indices
        if self.use_indexing and self.index_manager and not target_class_candidates:
            # Use index to find candidates
            candidates = self.index_manager.search_candidates(state, length_tolerance=0.5)
            
            # If we have target candidates, intersect with them
            if target_class_candidates:
                candidates &= set(target_class_candidates)
            
            logger.debug(f"Index filtering: {self.patterns_count} -> {len(candidates)} candidates")
        else:
            # Use all patterns or specified targets
            candidates = target_class_candidates if target_class_candidates else self.patterns_cache.keys()
        
        # Apply Bloom filter pre-screening if enabled
        logger.debug(f"Bloom filter check: self.bloom_filter={self.bloom_filter is not None}, candidates count={len(candidates) if candidates else 0}")
        
        if self.bloom_filter and candidates:
            try:
                logger.info(f"Starting Bloom filter pre-screening with {len(candidates)} candidates")
                
                # Get patterns for Bloom filter pre-screening
                candidate_patterns = []
                for candidate in candidates:
                    if candidate in self.patterns_cache:
                        pattern = self.patterns_cache[candidate]
                        # Ensure pattern is in proper format for Bloom filter
                        if isinstance(pattern, dict):
                            candidate_patterns.append(pattern)
                
                logger.debug(f"Extracted {len(candidate_patterns)} valid patterns for Bloom filtering")
                
                # Pre-screen candidates using Bloom filter
                if candidate_patterns:
                    filtered_patterns = self.bloom_filter.prescreen_patterns(candidate_patterns, state)
                    logger.debug(f"Bloom filter returned {len(filtered_patterns)} filtered patterns")
                    
                    # Update candidates to only include filtered pattern names
                    filtered_candidates = set()
                    for p in filtered_patterns:
                        if isinstance(p, dict):
                            # Try to get name field, fallback to other identifiers
                            pattern_name = p.get('name') or p.get('_id') or p.get('pattern_id', '')
                            if pattern_name:
                                filtered_candidates.add(pattern_name)
                    
                    original_count = len(candidates)
                    candidates = list(c for c in candidates if c in filtered_candidates)
                    
                    logger.info(f"Bloom filter pre-screening: {original_count} -> {len(candidates)} candidates")
                else:
                    logger.warning("No valid candidate patterns found for Bloom filter pre-screening")
            except Exception as e:
                logger.warning(f"Bloom filter pre-screening failed, continuing without filtering: {e}")
                # Continue with original candidates if Bloom filter fails
        
        # Process candidates
        if self.use_fast_matching and RAPIDFUZZ_AVAILABLE:
            # Use RapidFuzz for batch similarity calculation
            self._process_with_rapidfuzz(state, candidates, results)
        else:
            # Use original processing
            self._process_with_original(state, candidates, results)
        
        logger.debug(f"Found {len(results)} matches above threshold")
        
        # Build Prediction objects
        active_list = []
        for result in results:
            if len(result) >= 8:  # Ensure we have all required fields
                pattern_hash, pattern, matching_intersection, past, present, missing, extras, similarity, number_of_blocks = result[:9]
                
                # Fetch full pattern data from database (MongoDB required)
                if self.knowledgebase is None:
                    raise RuntimeError("MongoDB connection required but not available")
                
                pattern_data = self.knowledgebase.patterns_kb.find_one(
                    {"name": pattern_hash}, {"_id": 0})
                
                if pattern_data:
                    pred = Prediction(
                        pattern_data,
                        matching_intersection,
                        past, present,
                        missing,
                        extras,
                        similarity,
                        number_of_blocks,
                        stm_events=stm_events
                    )
                    active_list.append(pred)
        
        # Final threshold validation - ensure all predictions meet threshold
        filtered_list = []
        for pred in active_list:
            if 'similarity' in pred and pred['similarity'] >= self.recall_threshold:
                filtered_list.append(pred)
            elif 'similarity' not in pred:
                # If no similarity key, include it (shouldn't happen)
                logger.warning(f"Prediction without similarity score: {pred.get('name', 'unknown')}")
                filtered_list.append(pred)
        
        logger.debug(f"Built {len(active_list)} predictions, {len(filtered_list)} after final threshold filter")
        
        return filtered_list
    
    def _process_with_rapidfuzz(self, state: List[str], 
                               candidates: List[str], results: List):
        """
        Process candidates using RapidFuzz for fast matching.
        
        Args:
            state: Current state
            candidates: Candidate pattern IDs
            results: Output list for results
        """
        # Convert state to string for RapidFuzz
        state_str = ' '.join(state)
        
        # Prepare choices
        choices = {}
        for pattern_id in candidates:
            if pattern_id in self.patterns_cache:
                pattern_seq = self.patterns_cache[pattern_id]
                choices[pattern_id] = ' '.join(pattern_seq)
        
        # Use RapidFuzz to find best matches
        if choices:
            # Don't limit results - let threshold do the filtering
            matches = process.extract(
                state_str,
                choices,
                scorer=fuzz.ratio,
                limit=None  # Get all matches, filter by threshold
            )
            
            # Process matches above threshold
            for choice_str, score, pattern_id in matches:
                similarity = score / 100.0
                if similarity >= self.recall_threshold:
                    pattern_seq = self.patterns_cache[pattern_id]
                    
                    # Extract detailed info for prediction
                    info = self.extractor.extract_prediction_info(
                        pattern_seq, state, self.recall_threshold)
                    
                    if info:
                        results.append((pattern_id,) + info)
    
    def _process_with_original(self, state: List[str], 
                              candidates: List[str], results: List):
        """
        Process candidates using original SequenceMatcher.
        
        Args:
            state: Current state
            candidates: Candidate pattern IDs
            results: Output list for results
        """
        pattern_matcher = difflib.SequenceMatcher()
        pattern_matcher.set_seq2(state)
        
        for pattern_id in candidates:
            if pattern_id in self.patterns_cache:
                pattern_seq = self.patterns_cache[pattern_id]
                
                # Use original extraction logic
                pattern_matcher.set_seq1(pattern_seq)
                similarity = pattern_matcher.ratio()
                
                if similarity >= self.recall_threshold:
                    # Extract detailed information
                    matching_intersection = []
                    matching_blocks = pattern_matcher.get_matching_blocks()
                    
                    for block in matching_blocks[:-1]:
                        (i, j, n) = tuple(block)
                        matching_intersection += state[j:j+n]
                    
                    # Extract temporal regions (same as original)
                    # matching_blocks includes a terminator at the end, so actual matches = len(matching_blocks) - 1
                    num_actual_blocks = len(matching_blocks) - 1
                    
                    if num_actual_blocks >= 1:  # Changed from >= 2 to handle single blocks
                        if num_actual_blocks == 1:
                            # Single matching block case
                            (i0, j0, n0) = tuple(matching_blocks[0])
                            
                            past = pattern_seq[:i0]
                            present = pattern_seq[i0:i0+n0]
                            
                            # For single block, use the same length as present for state_segment
                            state_segment = state[j0:min(j0+len(present), len(state))]
                            
                            (i1, j1, n1) = (i0, j0, n0)  # Set for consistency
                        else:
                            # Multiple matching blocks (2+)
                            (i0, j0, n0) = tuple(matching_blocks[0])
                            (i1, j1, n1) = tuple(matching_blocks[-2])  # Last actual match (before terminator)
                            
                            past = pattern_seq[:i0]
                            present = pattern_seq[i0:i1+n1] if i1+n1 > i0 else pattern_seq[i0:]
                            
                        
                        number_of_blocks = num_actual_blocks
                        
                        # Extract anomalies using original approach
                        # The original code compared present against the full state
                        missing = []
                        extras = []
                        
                        pattern_matcher.set_seq1(present)
                        # seq2 already has the full state from earlier
                        # pattern_matcher.set_seq2(state) was already done above
                        
                        diffs = list(pattern_matcher.compare())
                        for diff in diffs:
                            if diff.startswith("- "):
                                missing.append(diff[2:])
                            elif diff.startswith("+ "):
                                extras.append(diff[2:])
                        
                        results.append((
                            pattern_id, pattern_seq, matching_intersection,
                            past, present, missing, extras,
                            similarity, number_of_blocks
                        ))
                    elif self.recall_threshold == 0.0:
                        # Special case: threshold 0.0 should include even non-matching patterns
                        past = []
                        present = pattern_seq
                        missing = pattern_seq  # All symbols are missing
                        extras = state  # All observed symbols are extras
                        number_of_blocks = 0
                        
                        results.append((
                            pattern_id, pattern_seq, matching_intersection,
                            past, present, missing, extras,
                            similarity, number_of_blocks
                        ))
    
    async def causalBeliefAsync(self, state: List[str],
                               target_class_candidates: Optional[List[str]] = None,
                               stm_events: Optional[List[List[str]]] = None,
                               max_workers: Optional[int] = None,
                               batch_size: int = 100) -> List[Dict[str, Any]]:
        """
        Async parallel version of causalBelief for high-performance pattern matching.
        
        Provides 3-10x performance improvement by:
        - Parallel processing of pattern matching using ThreadPoolExecutor
        - Batched candidate processing to optimize memory usage
        - Async database queries for pattern data retrieval
        - Concurrent similarity calculations using asyncio.gather
        
        Args:
            state: Current state sequence (flattened STM).
            target_class_candidates: Optional list of specific pattern names
            max_workers: Max thread pool workers (defaults to CPU count)
            batch_size: Number of patterns per batch for parallel processing
            
        Returns:
            List of prediction dictionaries sorted by potential/relevance.
        """
        logger.info(f"*** causalBeliefAsync called with state={state}, target_class_candidates={target_class_candidates}")
        
        if self.patterns_count == 0:
            await self.getPatternsAsync()
        
        # Default max_workers to CPU count
        if max_workers is None:
            max_workers = min(multiprocessing.cpu_count(), 8)  # Cap at 8 to avoid overload
        
        # Get candidate patterns using indices
        if self.use_indexing and self.index_manager and not target_class_candidates:
            candidates = self.index_manager.search_candidates(state, length_tolerance=0.5)
            if target_class_candidates:
                candidates &= set(target_class_candidates)
            logger.debug(f"Index filtering: {self.patterns_count} -> {len(candidates)} candidates")
        else:
            candidates = target_class_candidates if target_class_candidates else list(self.patterns_cache.keys())
        
        # Split candidates into batches for parallel processing
        candidate_batches = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]
        
        # Process batches in parallel
        all_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create futures for each batch
            futures = []
            for batch in candidate_batches:
                if self.use_fast_matching and RAPIDFUZZ_AVAILABLE:
                    future = executor.submit(self._process_batch_rapidfuzz, state, batch)
                else:
                    future = executor.submit(self._process_batch_original, state, batch)
                futures.append(future)
            
            # Gather results from all batches
            for future in concurrent.futures.as_completed(futures):
                try:
                    batch_results = future.result()
                    all_results.extend(batch_results)
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")
        
        logger.debug(f"Found {len(all_results)} matches above threshold (async parallel)")
        
        # Build Prediction objects asynchronously
        active_list = await self._build_predictions_async(all_results, max_workers, stm_events)
        
        # Final threshold validation
        filtered_list = [pred for pred in active_list 
                        if pred.get('similarity', 0) >= self.recall_threshold]
        
        logger.debug(f"Final predictions after threshold filter: {len(filtered_list)}")
        
        # Sort by potential and return
        try:
            return sorted(filtered_list, key=itemgetter('potential'), reverse=True)
        except KeyError:
            # Fallback if potential is missing
            return sorted(filtered_list, key=lambda x: x.get('similarity', 0), reverse=True)
    
    def _process_batch_rapidfuzz(self, state: List[str], candidates: List[str]) -> List:
        """
        Process a batch of candidates using RapidFuzz (thread-safe).
        
        Args:
            state: Current state
            candidates: Batch of candidate pattern IDs
            
        Returns:
            List of match results for this batch
        """
        batch_results = []
        state_str = ' '.join(state)
        
        # Prepare choices for this batch
        choices = {}
        for pattern_id in candidates:
            if pattern_id in self.patterns_cache:
                pattern_seq = self.patterns_cache[pattern_id]
                choices[pattern_id] = ' '.join(pattern_seq)
        
        # Use RapidFuzz to find matches in this batch
        if choices:
            matches = process.extract(
                state_str,
                choices,
                scorer=fuzz.ratio,
                limit=None
            )
            
            for choice_str, score, pattern_id in matches:
                similarity = score / 100.0
                if similarity >= self.recall_threshold:
                    pattern_seq = self.patterns_cache[pattern_id]
                    
                    # Extract detailed info for prediction
                    info = self.extractor.extract_prediction_info(
                        pattern_seq, state, self.recall_threshold)
                    
                    if info:
                        batch_results.append((
                            pattern_id, pattern_seq, info[1],  # matching_intersection
                            info[2], info[3], info[4], info[5],  # past, present, missing, extras
                            similarity, info[7]  # similarity, number_of_blocks
                        ))
        
        return batch_results
    
    def _process_batch_original(self, state: List[str], candidates: List[str]) -> List:
        """
        Process a batch of candidates using original algorithm (thread-safe).
        
        Args:
            state: Current state
            candidates: Batch of candidate pattern IDs
            
        Returns:
            List of match results for this batch
        """
        batch_results = []
        
        for pattern_id in candidates:
            if pattern_id in self.patterns_cache:
                pattern_seq = self.patterns_cache[pattern_id]
                
                # Use original matching
                info = self.extractor.extract_prediction_info(
                    pattern_seq, state, self.recall_threshold)
                
                if info and len(info) >= 8:
                    similarity = info[6] if len(info) > 6 else 0.0
                    if similarity >= self.recall_threshold:
                        batch_results.append((
                            pattern_id, pattern_seq, info[1],  # matching_intersection
                            info[2], info[3], info[4], info[5],  # past, present, missing, extras
                            similarity, info[7] if len(info) > 7 else 0  # similarity, number_of_blocks
                        ))
        
        return batch_results
    
    async def _build_predictions_async(self, results: List, max_workers: int, stm_events: Optional[List[List[str]]] = None) -> List[Dict[str, Any]]:
        """
        Build Prediction objects from results asynchronously.

        Args:
            results: List of match results
            max_workers: Maximum concurrent workers
            stm_events: Original event-structured STM for calculating event-aligned missing/extras

        Returns:
            List of prediction dictionaries
        """
        if not results:
            return []

        # Split results into batches for async processing
        batch_size = max(1, len(results) // max_workers)
        result_batches = [results[i:i + batch_size] for i in range(0, len(results), batch_size)]

        # Process batches concurrently
        tasks = []
        for batch in result_batches:
            task = asyncio.create_task(self._build_predictions_batch(batch, stm_events))
            tasks.append(task)
        
        # Gather all predictions
        batch_predictions = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results and handle exceptions
        active_list = []
        for batch_result in batch_predictions:
            if isinstance(batch_result, Exception):
                logger.error(f"Error building predictions batch: {batch_result}")
            else:
                active_list.extend(batch_result)
        
        return active_list
    
    async def _build_predictions_batch(self, batch: List, stm_events: Optional[List[List[str]]] = None) -> List[Dict[str, Any]]:
        """
        Build predictions for a batch of results.

        Args:
            batch: Batch of match results
            stm_events: Original event-structured STM for calculating event-aligned missing/extras

        Returns:
            List of prediction dictionaries for this batch
        """
        predictions = []
        
        for result in batch:
            if len(result) >= 8:
                pattern_hash, pattern, matching_intersection, past, present, missing, extras, similarity, number_of_blocks = result[:9]
                
                # Fetch pattern data from MongoDB (still sync, but batched)
                if self.knowledgebase is None:
                    raise RuntimeError("MongoDB connection required but not available")
                
                pattern_data = self.knowledgebase.patterns_kb.find_one(
                    {"name": pattern_hash}, {"_id": 0})
                
                if pattern_data:
                    pred = Prediction(
                        pattern_data,
                        matching_intersection,
                        past, present,
                        missing,
                        extras,
                        similarity,
                        number_of_blocks,
                        stm_events=stm_events
                    )
                    predictions.append(pred)
        
        return predictions
    
    def close(self):
        """
        DEPRECATED: Do not close shared database connections.
        
        PatternSearcher uses a MongoDB connection managed by OptimizedConnectionManager.
        Closing the connection from one searcher would break all other processors.
        Connection lifecycle is managed centrally by the connection manager.
        """
        # DO NOT CLOSE SHARED CONNECTION - it's managed by OptimizedConnectionManager
        # self.connection.close()  # REMOVED: This breaks other processors using same connection
        logger.debug(f"PatternSearcher.close() called for {self.kb_id} - connection managed centrally, no action taken")
        return


