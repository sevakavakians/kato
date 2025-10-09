import logging
from collections import Counter
from itertools import chain

from pymongo import ASCENDING, DESCENDING

from kato.config.settings import get_settings

logger = logging.getLogger('kato.informatics.knowledge-base')
# Configure logging lazily
logger.info('logging initiated')


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
    "KnowledgeBase database that can be combined with other KBs"
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

        logger.info(f" Attaching knowledgebase for {self.id} using optimized connection manager ...")
        try:
            # Use optimized connection manager for improved performance and reliability
            from kato.storage.connection_manager import get_mongodb_client
            self.connection = get_mongodb_client()

            # Test the connection
            self.connection.admin.command('ping')
            logger.info(" MongoDB connection successful via optimized connection manager")
            # CRITICAL FIX: Changed from w=0 (fire-and-forget) to w="majority" for data durability
            self.write_concern = {"w": "majority", "j": True}  # v2.0: Ensure write acknowledgment
            self.knowledge = self.connection[self.id]
            self.patterns_kb = self.knowledge.patterns_kb
            self.symbols_kb = self.knowledge.symbols_kb
            self.associative_action_kb = self.knowledge.associative_action_kb
            self.predictions_kb = self.knowledge.predictions_kb
            self.metadata = self.knowledge.metadata

            # Primary indexes for unique lookups
            # Patterns are keyed by hash of their pattern data
            self.patterns_kb.create_index( [("name", ASCENDING)], background=1, unique=1 )
            # Symbols are unique string/vector identifiers
            self.symbols_kb.create_index( [("name", ASCENDING)], background=1, unique=1 )
            # Actions associated with symbols
            self.associative_action_kb.create_index( [("symbol", ASCENDING)], background=1 )

            # Compound indexes for optimized queries
            # For finding high-frequency patterns quickly
            self.patterns_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
            # For pattern matching operations
            self.patterns_kb.create_index([("pattern_data", ASCENDING), ("name", ASCENDING)], background=1)
            # For symbol frequency queries
            self.symbols_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
            # For retrieving predictions by observation ID
            self.predictions_kb.create_index([("unique_id", ASCENDING), ("time", DESCENDING)], background=1)

            self.patterns_kb.learnPattern = self.learnPattern
            self.associative_action_kb.learnAssociation = self.learnAssociation

            self.patterns_kb.__pkb_repr__ = self.__pkb_repr__
            self.associative_action_kb.__akb_repr__ = self.__akb_repr__

            self.total_utility = None
            self.emotives_available = set()
            self.total_information = None
            self.entropy = None
            self.histogram = None

            if not self.metadata.find_one({"class": "totals"}):
                self.metadata.insert_one({"class": "totals",
                                    "total_pattern_frequencies": 0,
                                    "total_symbol_frequencies": 0,
                                    "total_symbols_in_patterns_frequencies": 0})
            logger.info("done.")
        except Exception as e:
            logger.error("FAILED! Exception: {}".format(e))
            raise Exception("\nFAILED! KnowledgeBase Exception: {}".format(e))
        return

    def clear_all_memory(self):
        """
        Core machine learning function.
        Used only if there is a need to clear out the entire knowledgebase.
        """
        self.connection.drop_database(self.id)

        self.patterns_kb.drop()
        self.symbols_kb.drop()
        self.associative_action_kb.drop()
        self.predictions_kb.drop()
        self.metadata.drop()
        self.metadata.insert_one({"class": "totals",
                            "total_pattern_frequencies": 0,
                            "total_symbol_frequencies": 0,
                            "total_symbols_in_patterns_frequencies": 0})
        # Recreate indexes after clearing
        self.patterns_kb.create_index([("name", ASCENDING)], background=1, unique=1)
        self.symbols_kb.create_index([("name", ASCENDING)], background=1, unique=1)
        self.associative_action_kb.create_index([("symbol", ASCENDING)], background=1)

        # Compound indexes
        self.patterns_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
        self.patterns_kb.create_index([("pattern_data", ASCENDING), ("name", ASCENDING)], background=1)
        self.symbols_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
        self.predictions_kb.create_index([("unique_id", ASCENDING), ("time", DESCENDING)], background=1)

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
        Use this to learn patterns by passing a Pattern object.  Optional keywords available.
        """
        if emotives is None:
            emotives = {}
        if metadata is None:
            metadata = {}

        try:
            # Build update operations
            update_ops = {
                "$setOnInsert": {
                    "pattern_data": pattern_object.pattern_data,
                    "length": pattern_object.length
                },
                "$inc": {"frequency": 1}
            }

            # Handle emotives (rolling window with $push and $slice)
            if emotives:
                self.emotives_available.update(emotives.keys())
                emotives = {k: v for k, v in emotives.items() if v != 0}
                update_ops["$push"] = {
                    "emotives": {"$each": [emotives], "$slice": -1 * self.persistence}
                }
            else:
                update_ops["$setOnInsert"]["emotives"] = {}

            # Handle metadata (accumulate unique string lists)
            if metadata:
                # Use $addToSet to append unique values to each metadata key's list
                add_to_set_ops = {}
                for key, values in metadata.items():
                    # values is already a list of strings from accumulate_metadata()
                    add_to_set_ops[f"metadata.{key}"] = {"$each": values}

                if add_to_set_ops:
                    update_ops["$addToSet"] = add_to_set_ops
            else:
                update_ops["$setOnInsert"]["metadata"] = {}

            # Execute the update
            result = self.patterns_kb.update_one(
                {"name": pattern_object.name},
                update_ops,
                upsert=True
            )

            # Update symbol statistics for all symbols in this pattern
            # Count occurrences of each symbol across the entire pattern data
            symbols = Counter(list(chain(*pattern_object.pattern_data)))

            # Prepare emotive updates for MongoDB dot notation
            __s = {}
            for emotive, value in emotives.items():
                __s["emotives.{}".format(emotive)] = value

            # Track symbol statistics:
            # - pattern_member_frequency: how many patterns contain this symbol
            # - frequency: total occurrences of this symbol
            __x = {"pattern_member_frequency": 1}
            total_symbols_in_patterns_frequencies = len(symbols)
            total_pattern_frequencies = 1

            # Update each symbol's statistics in the database
            for symbol, c in symbols.items():
                __x["frequency"] = c  # How many times symbol appears in this pattern
                __x.update(__s)  # Add emotive values

                # Atomic upsert: increment counters or create new entry
                self.symbols_kb.update_one({ "name": symbol},
                                        {"$inc": {**__x},  # Increment all counters
                                        "$setOnInsert": {"name": symbol}  # Set name on first insert
                                        },
                                        upsert=True)

            # if result.matched_count: # then these symbols have already been counted for this pattern.
            #     __x = {}
            #     total_symbols_in_patterns_frequencies = 0
            #     total_pattern_frequencies = 0
            # else: # then these symbols have NOT already been counted for this pattern.
            #     __x = {"pattern_member_frequency": 1}
            #     total_symbols_in_patterns_frequencies = len(symbols)
            #     total_pattern_frequencies = 1
            # for symbol, c in symbols.items():
            #     __x["frequency"] = c
            #     __x.update(__s)
            #     self.symbols_kb.update_one({ "name": symbol},
            #                             {"$inc": {**__x},
            #                             "$setOnInsert": {"name": symbol}
            #                             },
            #                             upsert=True)

            ## Update totals in metadata:

            total_symbol_frequencies = sum(symbols.values())

            self.metadata.update_one({"class": "totals"},
                                      {"$inc": {"total_pattern_frequencies": total_pattern_frequencies,
                                                "total_symbol_frequencies": total_symbol_frequencies,
                                                "total_symbols_in_patterns_frequencies": total_symbols_in_patterns_frequencies}})

            return not result.matched_count ### If 1, then this was known, so return False to be "new"

        except Exception as e:
            raise Exception("\nException in learnPattern: {}, \n{}".format(pattern_object.name, e))

    def getPattern(self, pattern, by="name"):
        """
        Core machine learning function.
        Retrieves a specific learned pattern using the pattern's hashed name as input parameter.
        """
        try:
            return self.patterns_kb.find_one({by: pattern})
        except Exception as e:
            raise Exception("\nException in getPattern ({}): {}".format(pattern, e))

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
