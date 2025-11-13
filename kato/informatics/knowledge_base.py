import logging
from collections import Counter
from itertools import chain

from pymongo import ASCENDING, DESCENDING

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
            self.symbols_kb = self._create_stub_collection_interface()
            self.predictions_kb = self._create_stub_collection_interface()
            self.associative_action_kb = self._create_stub_collection_interface()
            self.metadata = self._create_stub_collection_interface()

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

    def _create_stub_collection_interface(self):
        """Create a stub interface for MongoDB collections during migration."""
        class StubCollection:
            def __init__(self):
                pass

            def delete_many(self, query):
                """Stub for delete_many (no-op during migration)."""
                return type('DeleteResult', (), {'deleted_count': 0})()

            def insert_one(self, document):
                """Stub for insert_one (no-op during migration)."""
                return type('InsertResult', (), {'inserted_id': None})()

            def update_one(self, filter, update, **kwargs):
                """Stub for update_one (no-op during migration)."""
                return type('UpdateResult', (), {'matched_count': 0, 'modified_count': 0})()

            def find_one(self, filter, **kwargs):
                """Stub for find_one (returns None)."""
                return None

            def find(self, *args, **kwargs):
                """Stub for find (returns empty list)."""
                return []

            def count_documents(self, query):
                """Stub for count_documents (returns 0)."""
                return 0

        return StubCollection()

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

    def __akb_repr__(self):
        return "{{KB| objects: {} }}".format(self.associative_action_kb.count_documents({}))

    def __vkb_repr__(self):
        return "{KB| vectors: 0 }"  # Vectors now handled by modern vector store

    # learnVector method removed - vectors now handled by modern vector store

    def learnAssociation(self, action, symbols):
        """
        Used by Decision Engine when ActionManipulatives are attached.
        """
        for symbol in symbols:
            x = self.associative_action_kb.update_one({ "name": symbol, "action": action },
                                              {"$inc": { "frequency": 1}},
                                              upsert=True)
        return x

    def updateSymbols(self, symbol, frequency):
        "Used by information analyzer and potential calculation."
        r = self.symbols_kb.update_one({ 'name': symbol },
                                        {'$inc': { 'frequency': frequency}},
                                         upsert=True)
        return r

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
