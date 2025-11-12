"""
MinHash/LSH-based pattern filter for approximate similarity at billion scale.

Uses Locality-Sensitive Hashing to find patterns with high Jaccard similarity
without computing exact pairwise comparisons.
"""

from typing import Optional, Set, Dict, Any
import logging

from datasketch import MinHash, MinHashLSH

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)


class MinHashFilter(PatternFilter):
    """
    Filter patterns using MinHash/LSH for approximate Jaccard similarity.

    This is a HYBRID filter that uses both database-side and Python-side stages:

    Stage 1 (Database): Query patterns with matching LSH bands
    - Compute STM's MinHash signature and LSH bands
    - Query ClickHouse for patterns where ANY LSH band matches
    - Reduces billions → millions with 99% candidate reduction

    Stage 2 (Python): Verify estimated Jaccard similarity
    - Load MinHash signatures for candidate patterns
    - Estimate Jaccard similarity using MinHash
    - Keep patterns where estimated_jaccard >= threshold

    Configuration:
        - minhash_threshold (default: 0.7): Estimated Jaccard threshold
        - minhash_bands (default: 20): Number of LSH bands
        - minhash_rows (default: 5): Rows per LSH band
        - minhash_num_hashes (default: 100): Total MinHash signature size

    Mathematics:
        - bands × rows = num_hashes (e.g., 20 × 5 = 100)
        - Probability of collision: P(collision) ≈ 1 - (1 - J^r)^b
          where J = Jaccard similarity, r = rows, b = bands
        - With b=20, r=5: Patterns with J≥0.7 have ~95% collision probability
    """

    def __init__(self, config: Any, state: list[str]):
        """
        Initialize MinHash/LSH filter.

        Args:
            config: SessionConfiguration with minhash parameters
            state: Current STM state (flattened token list)
        """
        super().__init__(config, state)

        # Get configuration with defaults
        self.threshold = getattr(config, 'minhash_threshold', None) or 0.7
        self.bands = getattr(config, 'minhash_bands', None) or 20
        self.rows = getattr(config, 'minhash_rows', None) or 5
        self.num_hashes = getattr(config, 'minhash_num_hashes', None) or 100

        # Validate bands × rows = num_hashes
        if self.bands * self.rows != self.num_hashes:
            logger.warning(
                f"MinHash configuration mismatch: bands({self.bands}) × rows({self.rows}) "
                f"!= num_hashes({self.num_hashes}). Adjusting bands to {self.num_hashes // self.rows}."
            )
            self.bands = self.num_hashes // self.rows

        # Compute STM MinHash signature and LSH bands
        self.stm_minhash = MinHash(num_perm=self.num_hashes)
        for token in self.stm_tokens:
            self.stm_minhash.update(token.encode('utf-8'))

        # Compute LSH bands for database query
        self.stm_lsh_bands = self._compute_lsh_bands(self.stm_minhash)

        logger.debug(
            f"MinHashFilter initialized: STM tokens={len(self.stm_tokens)}, "
            f"threshold={self.threshold}, bands={self.bands}, rows={self.rows}, "
            f"num_hashes={self.num_hashes}, lsh_bands={len(self.stm_lsh_bands)}"
        )

    def _compute_lsh_bands(self, minhash: MinHash) -> list[int]:
        """
        Compute LSH band hashes from MinHash signature.

        Splits MinHash signature into bands and hashes each band.

        Args:
            minhash: MinHash object with signature

        Returns:
            List of band hashes (one per band)
        """
        signature = minhash.hashvalues
        bands = []

        for i in range(self.bands):
            # Extract rows for this band
            start_idx = i * self.rows
            end_idx = start_idx + self.rows
            band_values = tuple(signature[start_idx:end_idx])

            # Hash the band (Python's built-in hash is sufficient)
            band_hash = hash(band_values)
            bands.append(band_hash)

        return bands

    def get_db_query(self) -> Optional[str]:
        """
        Generate ClickHouse SQL query for LSH band matching.

        Queries patterns where ANY of their LSH bands matches ANY of STM's bands.

        Returns:
            SQL query string for LSH band matching
        """
        # Convert LSH bands to ClickHouse array literal
        # Note: ClickHouse uses UInt64 for band hashes, handle negative hash values
        bands_str = ", ".join(str(abs(band)) for band in self.stm_lsh_bands)
        bands_array = f"[{bands_str}]"

        query = f"""
        SELECT name, pattern_data, minhash_sig
        FROM patterns_data
        WHERE hasAny(lsh_bands, {bands_array})
        """

        return query

    def filter_python(self, candidates: Set[str], patterns_cache: Dict[str, Any]) -> Set[str]:
        """
        Python-side filtering: Verify estimated Jaccard similarity.

        This is the SECOND stage of MinHashFilter, called after database stage.

        Args:
            candidates: Set of pattern names (from database query)
            patterns_cache: Dict mapping pattern names to pattern data
                Expected keys per pattern: 'minhash_sig' (list of hash values)

        Returns:
            Filtered set of patterns with estimated Jaccard >= threshold
        """
        if not candidates:
            return set()

        filtered = set()

        for pattern_name in candidates:
            pattern_data = patterns_cache.get(pattern_name)
            if not pattern_data:
                logger.warning(f"Pattern '{pattern_name}' not in cache, skipping")
                continue

            # Extract MinHash signature from cached data
            # Note: Database query should include 'minhash_sig' field
            minhash_sig = pattern_data.get('minhash_sig')
            if not minhash_sig:
                logger.warning(f"Pattern '{pattern_name}' missing minhash_sig, skipping")
                continue

            # Reconstruct MinHash object from signature
            pattern_minhash = MinHash(num_perm=self.num_hashes)
            pattern_minhash.hashvalues = minhash_sig

            # Estimate Jaccard similarity
            estimated_jaccard = self.stm_minhash.jaccard(pattern_minhash)

            # Keep pattern if estimated Jaccard >= threshold
            if estimated_jaccard >= self.threshold:
                filtered.add(pattern_name)

        logger.debug(
            f"MinHash Python-side filtering: {len(candidates)} candidates → "
            f"{len(filtered)} patterns (threshold={self.threshold})"
        )

        return filtered
