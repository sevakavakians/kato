import logging
from collections import Counter
from itertools import chain

from kato.config.settings import get_settings

logger = logging.getLogger('kato.informatics.knowledge-base')
# Configure logging lazily


class KnowledgeBase(dict):
    "KnowledgeBase database that can be combined with other KBs.  Currently used for ActionsKB."
    def __init__(self):
        "Provide the path and name of the KB.  An extension will automatically be given."
        self.total_utility = None
        self.total_information = None
        self.entropy = None
        self.histogram = None
        self.total_observation_count = 0
        return

    def count(self):
        return len(list(self.keys()))

    def __repr__(self):
        return "{{KB| objects: {}}}".format(len(list(self.keys())))

    def learnObject(self, object, utility=None, affinity=None):
        if object.name in list(self.keys()):
            if utility:
                self[object.name].utility += utility
            if affinity:
                self[object.name].updateAffinity(affinity)
            self[object.name].frequency += 1
            self.total_observation_count += 1
            return
        else:
            self.setdefault(object.name, object)
            if utility:
                object.utility += utility
            if affinity:
                self[object.name].updateAffinity(affinity)
            self.total_observation_count += 1
            return

class SuperKnowledgeBase:
    "KnowledgeBase database using ClickHouse + Redis for hybrid storage"
    def __init__(self, primitive_id, persistence=7, settings=None):
        "Provide the primitive's ID."
        self.id = primitive_id
        self.persistence = int(persistence)

        # Accept settings via dependency injection, fallback to get_settings() for compatibility
        if settings is None:
            settings = get_settings()

        # Configure logger level if not already set
        if logger.level == 0:  # Logger level not set
            logger.setLevel(getattr(logging, settings.logging.log_level))

        logger.info(f" Attaching knowledgebase for {self.id} using ClickHouse + Redis ...")
        try:
            # Get ClickHouse and Redis clients (REQUIRED)
            from kato.storage.connection_manager import get_clickhouse_client, get_redis_client
            from kato.storage.clickhouse_writer import ClickHouseWriter
            from kato.storage.redis_writer import RedisWriter

            clickhouse_client = get_clickhouse_client()
            redis_client = get_redis_client()

            if clickhouse_client is None:
                raise RuntimeError(
                    "ClickHouse client is required but not available. "
                    "Ensure ClickHouse is running: docker ps | grep clickhouse"
                )

            if redis_client is None:
                raise RuntimeError(
                    "Redis client is required but not available. "
                    "Ensure Redis is running: docker ps | grep redis"
                )

            # Initialize hybrid storage writers
            self.clickhouse_writer = ClickHouseWriter(self.id, clickhouse_client)
            self.redis_writer = RedisWriter(self.id, redis_client)

            # Set emotives tracking and observation counts
            self.emotives_available = set()
            self.total_utility = None
            self.total_information = None
            self.entropy = None
            self.histogram = None
            self.patterns_observation_count = 0

            # Create backward-compatible interfaces for MongoDB collections
            # These allow existing code to work without changes during migration
            self.patterns_kb = self._create_patterns_kb_interface()
            self.symbols_kb = self._create_symbols_kb_interface()
            self.metadata = self._create_metadata_interface()

            logger.info(f"SuperKnowledgeBase initialized for {self.id} with ClickHouse + Redis")
        except Exception as e:
            logger.error(f"FAILED! Exception: {e}")
            raise Exception(f"\nFAILED! KnowledgeBase Exception: {e}")
        return

    def _create_patterns_kb_interface(self):
        """Create a duck-typed interface for patterns_kb to maintain backward compatibility."""
        class PatternsKBInterface:
            def __init__(self, parent):
                self.parent = parent
                self.learnPattern = parent.learnPattern

            def count_documents(self, query):
                """Count patterns (for backward compatibility)."""
                return self.parent.clickhouse_writer.count_patterns()

            def delete_many(self, query):
                """Delete all patterns (delegates to clear_all_memory)."""
                self.parent.clickhouse_writer.delete_all_patterns()
                return type('DeleteResult', (), {'deleted_count': 0})()

            def __pkb_repr__(self):
                count = self.parent.clickhouse_writer.count_patterns()
                return f"{{KB| objects: {count} }}"

        return PatternsKBInterface(self)

    def _create_symbols_kb_interface(self):
        """Create a Redis-backed interface for symbols_kb to maintain backward compatibility."""
        class SymbolsKBInterface:
            def __init__(self, parent):
                self.parent = parent

            def find_one(self, filter, **kwargs):
                """
                Find one symbol matching filter.

                Args:
                    filter: Query dict, e.g., {"name": "symbol1"}

                Returns:
                    Symbol document dict or None
                """
                if 'name' not in filter:
                    raise ValueError("symbols_kb.find_one() requires 'name' in filter")

                symbol_name = filter['name']
                return self.parent.redis_writer.get_symbol_stats(symbol_name)

            def find(self, filter=None, projection=None, **kwargs):
                """
                Find all symbols matching filter.

                Args:
                    filter: Query dict (currently ignored, returns all)
                    projection: Field projection (currently ignored)

                Returns:
                    List of symbol documents
                """
                # Get all symbols from Redis
                symbols_dict = self.parent.redis_writer.get_all_symbols_batch()
                # Convert to list of documents
                return list(symbols_dict.values())

            def aggregate(self, pipeline, **kwargs):
                """
                Aggregate query for symbols (used by aggregation_pipelines.py).

                For now, this delegates to get_all_symbols_batch and mimics
                the aggregation behavior by returning symbol documents.

                Args:
                    pipeline: Aggregation pipeline (currently simplified)

                Returns:
                    List of symbol documents
                """
                # For the get_all_symbols_optimized use case, just return all symbols
                # The pipeline typically does projection and sorting
                symbols_dict = self.parent.redis_writer.get_all_symbols_batch()
                return list(symbols_dict.values())

            def count_documents(self, query):
                """
                Count symbols.

                Returns:
                    Number of unique symbols tracked
                """
                symbols_dict = self.parent.redis_writer.get_all_symbols_batch()
                return len(symbols_dict)

            def delete_many(self, query):
                """
                Delete all symbols (part of clear_all_memory).
                Symbol keys are deleted when clear_all_memory is called.

                Returns:
                    DeleteResult with deleted_count
                """
                # Symbols are deleted as part of redis_writer.delete_all_metadata()
                # which is called by clear_all_memory()
                return type('DeleteResult', (), {'deleted_count': 0})()

            def update_one(self, filter, update, **kwargs):
                """
                Update symbol (legacy method, not used in hybrid architecture).
                Symbol updates happen via increment methods in redis_writer.

                Returns:
                    UpdateResult indicating no-op
                """
                # Symbol updates happen via increment_symbol_frequency/increment_pattern_member_frequency
                # This method exists for backward compatibility but is a no-op
                logger.warning("symbols_kb.update_one() called but is deprecated in hybrid architecture")
                return type('UpdateResult', (), {'matched_count': 0, 'modified_count': 0})()

        return SymbolsKBInterface(self)

    def _create_metadata_interface(self):
        """Create Redis-backed metadata interface for global totals."""
        class MetadataInterface:
            def __init__(self, parent):
                self.parent = parent

            def find_one(self, filter, **kwargs):
                """
                Return global metadata matching MongoDB interface.

                Expected usage: metadata.find_one({"class": "totals"})
                Returns dict with total_symbols_in_patterns_frequencies and total_pattern_frequencies
                """
                if filter.get("class") == "totals":
                    return self.parent.redis_writer.get_global_metadata()
                return None

            def update_one(self, filter, update, **kwargs):
                """
                Update global metadata (no-op for now, updates happen via increment methods).
                """
                return type('UpdateResult', (), {'matched_count': 0, 'modified_count': 0})()

            def delete_many(self, query):
                """Delete metadata (handled by clear_all_memory)."""
                return type('DeleteResult', (), {'deleted_count': 0})()

            def count_documents(self, query):
                """Stub for count_documents."""
                return 0

        return MetadataInterface(self)

    def clear_all_memory(self):
        """
        Core machine learning function.
        Used only if there is a need to clear out the entire knowledgebase.
        Deletes all patterns from ClickHouse + Redis for this kb_id.
        """
        try:
            # Delete from ClickHouse (drop partition)
            self.clickhouse_writer.delete_all_patterns()
            logger.info(f"Dropped ClickHouse partition for kb_id: {self.id}")

            # Delete from Redis (delete all keys with kb_id prefix)
            deleted_count = self.redis_writer.delete_all_metadata()
            logger.info(f"Deleted {deleted_count} Redis keys for kb_id: {self.id}")

        except Exception as e:
            logger.error(f"Error clearing memory for {self.id}: {e}")
            raise

        return

    def __repr__(self):
        return "{{Patterns: {}, information: {}, entropy: {}}}".format(self.patterns_kb.count_documents({}), self.total_information, self.entropy)

    def __pkb_repr__(self):
        return "{{KB| objects: {} }}".format(self.patterns_kb.count_documents({}))

    def __vkb_repr__(self):
        return "{KB| vectors: 0 }"  # Vectors now handled by modern vector store

    # learnVector method removed - vectors now handled by modern vector store

    def learnPattern(self, pattern_object, emotives=None, metadata=None):
        """
        Core machine learning function.
        Store pattern in ClickHouse + Redis.

        Args:
            pattern_object: Pattern object with name, pattern_data, length
            emotives: Emotional context dictionary (optional)
            metadata: Additional metadata dictionary (optional)

        Returns:
            True if this is a new pattern, False if pattern already existed
        """
        if emotives is None:
            emotives = {}
        if metadata is None:
            metadata = {}

        try:
            logger.info(f"[HYBRID] learnPattern() called for {pattern_object.name}")

            # Track available emotives
            if emotives:
                self.emotives_available.update(emotives.keys())
                # Filter out zero emotives
                emotives = {k: v for k, v in emotives.items() if v != 0}

            # Check if pattern already exists in Redis
            logger.info(f"[HYBRID] Checking if pattern exists in Redis: {pattern_object.name}")
            existing_frequency = self.redis_writer.get_frequency(pattern_object.name)
            logger.info(f"[HYBRID] Existing frequency: {existing_frequency}")

            if existing_frequency > 0:
                # Pattern exists - increment frequency
                self.redis_writer.increment_frequency(pattern_object.name)
                logger.info(f"[HYBRID] Incremented frequency for pattern {pattern_object.name}")

                # Update symbol statistics (pattern seen again)
                from itertools import chain
                from collections import Counter

                # Flatten pattern_data to get all symbols
                all_symbols = list(chain(*pattern_object.pattern_data))
                symbol_count = len(all_symbols)

                # Count occurrences of each symbol in this pattern
                symbol_counts = Counter(all_symbols)

                # Increment symbol frequency for each symbol by its count in pattern
                for symbol, count in symbol_counts.items():
                    self.redis_writer.increment_symbol_frequency(symbol, count)
                    logger.debug(f"[HYBRID] Incremented symbol frequency for {symbol} by {count}")

                # Increment global symbol count (pattern seen again)
                self.redis_writer.increment_global_symbol_count(symbol_count)
                logger.debug(f"[HYBRID] Updated symbol stats: {len(symbol_counts)} unique symbols, {symbol_count} total")

                return False  # Not a new pattern

            else:
                # New pattern - write to both ClickHouse and Redis
                logger.info(f"[HYBRID] Writing NEW pattern to ClickHouse: {pattern_object.name}")
                # Write pattern data to ClickHouse
                self.clickhouse_writer.write_pattern(pattern_object)
                logger.info(f"[HYBRID] ClickHouse write completed for {pattern_object.name}")

                # Write metadata to Redis
                logger.info(f"[HYBRID] Writing metadata to Redis: {pattern_object.name}")
                self.redis_writer.write_metadata(
                    pattern_name=pattern_object.name,
                    frequency=1,
                    emotives=emotives if emotives else None,
                    metadata=metadata if metadata else None
                )
                logger.info(f"[HYBRID] Redis write completed for {pattern_object.name}")

                # Update symbol statistics for new pattern
                from itertools import chain
                from collections import Counter

                # Flatten pattern_data to get all symbols
                all_symbols = list(chain(*pattern_object.pattern_data))
                symbol_count = len(all_symbols)

                # Count occurrences of each symbol in this pattern
                symbol_counts = Counter(all_symbols)

                # For NEW pattern: update both frequency and pattern_member_frequency
                for symbol, count in symbol_counts.items():
                    # Increment symbol frequency by count (how many times it appears)
                    self.redis_writer.increment_symbol_frequency(symbol, count)
                    # Increment pattern_member_frequency by 1 (this pattern contains this symbol)
                    self.redis_writer.increment_pattern_member_frequency(symbol, 1)
                    logger.debug(f"[HYBRID] Tracked symbol {symbol}: freq+{count}, pmf+1")

                # Update global totals for new pattern
                self.redis_writer.increment_global_symbol_count(symbol_count)
                self.redis_writer.increment_global_pattern_count(1)
                logger.debug(f"[HYBRID] Updated global totals: {len(symbol_counts)} unique symbols, {symbol_count} total, +1 pattern")

                logger.info(f"[HYBRID] Successfully learned new pattern {pattern_object.name} to ClickHouse + Redis")
                return True  # New pattern

        except Exception as e:
            logger.error(f"[HYBRID] Exception in learnPattern: {pattern_object.name}, {e}")
            raise Exception(f"\nException in learnPattern: {pattern_object.name}, \n{e}")

    def getPattern(self, pattern, by="name"):
        """
        Core machine learning function.
        Retrieves a specific learned pattern using the pattern's hashed name as input parameter.

        Args:
            pattern: Pattern name (hash)
            by: Search field (default: "name")

        Returns:
            Dictionary with pattern data, or None if not found
        """
        try:
            # Get pattern data from ClickHouse
            pattern_data = self.clickhouse_writer.get_pattern_data(pattern)
            if not pattern_data:
                return None

            # Get metadata from Redis
            redis_metadata = self.redis_writer.get_metadata(pattern)

            # Combine ClickHouse and Redis data
            result = {
                'name': pattern,
                'pattern_data': pattern_data['pattern_data'],
                'length': pattern_data['length'],
                'frequency': redis_metadata.get('frequency', 1)
            }

            # Add emotives and metadata if present
            if 'emotives' in redis_metadata:
                result['emotives'] = redis_metadata['emotives']
            if 'metadata' in redis_metadata:
                result['metadata'] = redis_metadata['metadata']

            return result

        except Exception as e:
            raise Exception(f"\nException in getPattern ({pattern}): {e}")

    def getTargetedPatternNames(self, target_class):
        """
        Returns a list of pattern names that are classified by the target_class, i.e. target_class symbol is in the last event.
        This is needed for the pattern search algorithm because patterns are flattened by that point and have lost event information.
        """
        r = [x['name'] for x in list(self.patterns_kb.aggregate([{ '$addFields': { 'classification': { '$last': "$pattern_data" }  }},
                                { '$match': {'classification':  {'$all':[target_class]}    } },
                                { '$project': {"name": 1, "classification": 1}}
                                ]) ) ]
        return r

    # getVectors method removed - vectors now handled by modern vector store

    # getVector method removed - vectors now handled by modern vector store

    def close(self):
        """
        DEPRECATED: Do not close shared database connections.

        Individual processors share a MongoDB connection managed by OptimizedConnectionManager.
        Closing the connection from one processor would break all other processors.
        Connection lifecycle is managed centrally by the connection manager.
        """
        # DO NOT CLOSE SHARED CONNECTION - it's managed by OptimizedConnectionManager
        # self.connection.close()  # REMOVED: This breaks other processors using same connection
        logger.debug(f"KnowledgeBase.close() called for {self.id} - connection managed centrally, no action taken")
        return

    def drop_database(self):
        """
        Drop all data for this kb_id from ClickHouse + Redis.

        WARNING: This permanently deletes all data. Only use for:
        - Test processors (kb_id starts with 'test_')
        - Explicit cleanup operations

        This method is used during processor eviction to prevent resource leaks
        in test environments.
        """
        try:
            # Safety check: only drop test kb_ids
            if not self.id.startswith('test_'):
                logger.warning(f"Refusing to drop non-test kb_id: {self.id}")
                return False

            # Drop from ClickHouse
            self.clickhouse_writer.delete_all_patterns()
            logger.info(f"Dropped ClickHouse partition: {self.id}")

            # Drop from Redis
            self.redis_writer.delete_all_metadata()
            logger.info(f"Deleted Redis keys for kb_id: {self.id}")

            return True
        except Exception as e:
            logger.error(f"Error dropping database {self.id}: {e}")
            return False
