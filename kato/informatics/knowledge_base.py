import logging
from os import environ

from numpy import array
from pymongo import ASCENDING, DESCENDING, MongoClient

from kato.representations.vector_object import VectorObject

from collections import Counter
from itertools import chain

logger = logging.getLogger('kato.informatics.knowledge-base')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
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
        return "{KB| objects: %s}" %(len(list(self.keys())))

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
    def __init__(self, primitive_id, persistence=7):
        "Provide the primitive's ID."
        self.id = primitive_id
        self.persistence = int(persistence)
        logger.info(f" Attaching knowledgebase for {self.id} using {environ['MONGO_BASE_URL']} ...")
        try:
            ### MongoDB
            self.connection = MongoClient('%s' %environ['MONGO_BASE_URL'])
            self.write_concern = {"w": 0}
            self.knowledge = self.connection[self.id]
            self.models_kb = self.knowledge.models_kb
            self.symbols_kb = self.knowledge.symbols_kb
            self.associative_action_kb = self.knowledge.associative_action_kb
            self.vectors_kb = self.knowledge.vectors_kb
            self.predictions_kb = self.knowledge.predictions_kb
            self.metadata = self.knowledge.metadata

            # Primary indexes for unique lookups
            # Models are keyed by hash of their sequence
            self.models_kb.create_index( [("name", ASCENDING)], background=1, unique=1 )
            # Symbols are unique string/vector identifiers
            self.symbols_kb.create_index( [("name", ASCENDING)], background=1, unique=1 )
            # Actions associated with symbols
            self.associative_action_kb.create_index( [("symbol", ASCENDING)], background=1 )
            # Vector representations keyed by hash
            self.vectors_kb.create_index( [("name", ASCENDING)], background=1, unique=1 )
            
            # Compound indexes for optimized queries
            # For finding high-frequency models quickly
            self.models_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
            # For sequence matching operations
            self.models_kb.create_index([("sequence", ASCENDING), ("name", ASCENDING)], background=1)
            # For symbol frequency queries
            self.symbols_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
            # For retrieving predictions by observation ID
            self.predictions_kb.create_index([("unique_id", ASCENDING), ("time", DESCENDING)], background=1)

            setattr(self.vectors_kb, "values", self.getVectors)  ## TODO: Check to see if this is used anywhere.
            setattr(self.vectors_kb, "getVector", self.getVector)

            setattr(self.models_kb, "learnModel", self.learnModel)
            setattr(self.vectors_kb, "learnVector", self.learnVector)
            setattr(self.associative_action_kb, "learnAssociation", self.learnAssociation)

            setattr(self.models_kb, "__mkb_repr__", self.__mkb_repr__)
            setattr(self.associative_action_kb, "__akb_repr__", self.__akb_repr__)
            setattr(self.vectors_kb, "__repr__", self.__vkb_repr__)

            self.total_utility = None
            self.emotives_available = set()
            self.total_information = None
            self.entropy = None
            self.histogram = None
            
            if not self.metadata.find_one({"class": "totals"}):
                self.metadata.insert_one({"class": "totals",
                                    "total_model_frequencies": 0,
                                    "total_symbol_frequencies": 0,
                                    "total_symbols_in_models_frequencies": 0})
            logger.info("done.")
        except Exception as e:
            logger.error("FAILED! Exception: %s" %(e))
            raise Exception("\nFAILED! KnowledgeBase Exception: %s" %(e))
        return

    def clear_all_memory(self):
        """
        Core machine learning function.
        Used only if there is a need to clear out the entire knowledgebase.
        """
        self.connection.drop_database(self.id)
        
        self.models_kb.drop()
        self.symbols_kb.drop()
        self.associative_action_kb.drop()
        self.vectors_kb.drop()
        self.predictions_kb.drop()
        self.metadata.drop()
        self.metadata.insert_one({"class": "totals",
                            "total_model_frequencies": 0,
                            "total_symbol_frequencies": 0,
                            "total_symbols_in_models_frequencies": 0})
        # Recreate indexes after clearing
        self.models_kb.create_index([("name", ASCENDING)], background=1, unique=1)
        self.symbols_kb.create_index([("name", ASCENDING)], background=1, unique=1)
        self.associative_action_kb.create_index([("symbol", ASCENDING)], background=1)
        self.vectors_kb.create_index([("name", ASCENDING)], background=1, unique=1)
        
        # Compound indexes
        self.models_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
        self.models_kb.create_index([("sequence", ASCENDING), ("name", ASCENDING)], background=1)
        self.symbols_kb.create_index([("frequency", DESCENDING), ("name", ASCENDING)], background=1)
        self.predictions_kb.create_index([("unique_id", ASCENDING), ("time", DESCENDING)], background=1)

        return

    def __repr__(self):
        return "{Models: %s, information: %s, entropy: %s}" %(self.models_kb.count_documents({}), self.total_information, self.entropy)

    def __mkb_repr__(self):
        return "{KB| objects: %s }" %(self.models_kb.count_documents({}))

    def __akb_repr__(self):
        return "{KB| objects: %s }" %(self.associative_action_kb.count_documents({}))

    def __vkb_repr__(self):
        return "{KB| objects: %s }" %(self.vectors_kb.count_documents({}))

    def learnVector(self, vector):
        """
        Core machine learning function.
        Used only if input data includes vectors.
        """
        try:
            #x = self.vectors_kb.insert_one({ "name": vector.name, "vector": vector.vector.tolist() })
            #return x
            result = self.vectors_kb.update_one({ "name": vector.name},
                                       {"$setOnInsert": {"vector": vector.vector.tolist()}},
                                      upsert=True)
            return result
        except Exception as e:
            raise Exception("\nFailed to learn vector! %s" %e)

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

    def learnModel(self, model_object, emotives={}):
        """
        Core machine learning function.
        Use this to learn models by passing a Model object.  Optional keywords available.
        """
        
        try:
            if emotives:
                self.emotives_available.update(emotives.keys())
                emotives = {k: v for k, v in emotives.items() if v != 0}
                result = self.models_kb.update_one({ "name": model_object.name},
                                    {"$setOnInsert": {"sequence": model_object.sequence, "length": model_object.length},
                                    "$inc": { "frequency": 1 },
                                    "$push": {"emotives": {"$each": [emotives], "$slice": -1 * self.persistence}}},
                                    upsert=True)
            else:
                result = self.models_kb.update_one({ "name": model_object.name},
                                       {"$inc": { "frequency": 1 },
                                       "$setOnInsert": {"sequence": model_object.sequence,
                                                        "length": model_object.length,
                                                        "emotives": {} }},
                                      upsert=True)
            
            # Update symbol statistics for all symbols in this model
            # Count occurrences of each symbol across the entire sequence
            symbols = Counter(list(chain(*model_object.sequence)))
            
            # Prepare emotive updates for MongoDB dot notation
            __s = {}
            for emotive, value in emotives.items():
                __s["emotives.%s" %emotive] = value
            
            # Track symbol statistics:
            # - model_member_frequency: how many models contain this symbol
            # - frequency: total occurrences of this symbol
            __x = {"model_member_frequency": 1}
            total_symbols_in_models_frequencies = len(symbols)
            total_model_frequencies = 1
            
            # Update each symbol's statistics in the database
            for symbol, c in symbols.items():
                __x["frequency"] = c  # How many times symbol appears in this model
                __x.update(__s)  # Add emotive values
                
                # Atomic upsert: increment counters or create new entry
                self.symbols_kb.update_one({ "name": symbol},
                                        {"$inc": {**__x},  # Increment all counters
                                        "$setOnInsert": {"name": symbol}  # Set name on first insert
                                        },
                                        upsert=True)

            # if result.matched_count: # then these symbols have already been counted for this model.
            #     __x = {}
            #     total_symbols_in_models_frequencies = 0
            #     total_model_frequencies = 0
            # else: # then these symbols have NOT already been counted for this model.
            #     __x = {"model_member_frequency": 1}
            #     total_symbols_in_models_frequencies = len(symbols)
            #     total_model_frequencies = 1
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
                                      {"$inc": {"total_model_frequencies": total_model_frequencies,
                                                "total_symbol_frequencies": total_symbol_frequencies,
                                                "total_symbols_in_models_frequencies": total_symbols_in_models_frequencies}})
            
            return not result.matched_count ### If 1, then this was known, so return False to be "new"

        except Exception as e:
            raise Exception("\nException in learnModel: %s, \n%s" %(model_object.name, e))

    def getModel(self, model, by="name"):
        """
        Core machine learning function.
        Retrieves a specific learned model using the model's hashed name as input parameter.
        """
        try:
            return self.models_kb.find_one({by: model})
        except Exception as e:
            raise Exception("\nException in getModel (%s): %s" %(model, e))
    
    def getTargetedModelNames(self, target_class):
        """
        Returns a list of sequence names that are classified by the target_class, i.e. target_class symbol is in the last event.
        This is needed for the model pattern search algorithm because sequences are flattened by that point and have lost event information.
        """
        r = [x['name'] for x in list(self.models_kb.aggregate([{ '$addFields': { 'classification': { '$last': "$sequence" }  }},
                                { '$match': {'classification':  {'$all':[target_class]}    } },
                                { '$project': {"name": 1, "classification": 1}}
                                ]) ) ]
        return r

    def getVectors(self):
        """
        Core machine learning function if vectors are used.
        Retrieves full learned vector set for use in vector classification algorithms.
        """
        try:
            return [VectorObject(array(v["vector"])) for v in self.vectors_kb.find({}, {"_id": 0, "vector": 1})]
#            return [v["vector"] for v in self.vectors_kb.find({}, {"_id": 0, "vector": 1})]
        except Exception as e:
            raise Exception("\nException in getVectors: %s" %(e))

    def getVector(self, vector, by="name"):
        """
        Used only by external functions that require retrieval of a specific vector.
        Retrieved by vector hash name as input parameter.
        """
        try:
            vector = self.vectors_kb.find_one({by: vector}, {'_id': False, 'vector': True})
            if vector and 'vector' in vector:
                return vector['vector']
        except Exception as e:
            return None

    def close(self):
        """
        Closes the main database connection.
        """
        self.connection.close()
        return
