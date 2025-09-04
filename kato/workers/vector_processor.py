import logging
from os import environ
from functools import reduce

from numpy import array

from kato.representations.vector_object import VectorObject
from kato.searches.vector_search_engine import VectorIndexer

logger = logging.getLogger('kato.vector_processor')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))
logger.info('logging initiated')


class VectorProcessor:
    """
    Processes percept VectorObjects to determine the object representations.
    Uses modern Vector Indexer with Qdrant backend.
    """
    def __init__(self, procs_for_searches, **kwargs):
        logger.debug("Starting VectorProcessor...")
        self.name = "VectorProcessor"
        self.kb_id = kwargs["kb_id"]
        self.indexer_type = kwargs["indexer_type"]
        self.procs_for_searches = procs_for_searches
        self.initialize_vector_searcher()
        self.deferred_vectors_for_learning = []
        logger.debug("VectorProcessor ready!")
        return

    def clear_all_memory(self):
        logger.debug("In VectorProcessor clear all memory")
        self.deferred_vectors_for_learning = []
        if self.indexer_type == "VI":
            self.vector_indexer.clearPatternsFromRAM()
            self.round_robin_index = 0
            logger.debug("about to reset VectorIndexer")
            # Pass kb_id (processor_id) for Qdrant collection isolation
            self.vector_indexer = VectorIndexer(self.procs_for_searches, processor_id=self.kb_id)
        return

    def clear_stm(self):
        self.deferred_vectors_for_learning = []
        return

    def learn(self):
        # Vector learning now handled by modern vector store
        if self.indexer_type == "VI":
            self.vector_indexer.assignNewlyLearnedToWorkers(self.deferred_vectors_for_learning)
        self.deferred_vectors_for_learning = []
        return

    def initialize_vector_searcher(self):
        if self.indexer_type == "VI":
            self.round_robin_index = 0
            # Pass kb_id (processor_id) for Qdrant collection isolation
            self.vector_indexer = VectorIndexer(self.procs_for_searches, processor_id=self.kb_id)
        return

    def process(self, vector_data):
        logger.debug(vector_data)
        # Convert list of lists to numpy arrays
        vector_data = [array(v) for v in vector_data]
        logger.debug(vector_data)
        percept_vector = reduce(lambda x,y: x+y, vector_data)
        logger.debug(percept_vector)
        percept_vector = VectorObject(percept_vector)
        logger.debug(percept_vector)
        if self.indexer_type == "VI":
            nearest_vectors = self.vector_indexer.findNearestPoints(percept_vector)
            self.deferred_vectors_for_learning.append(percept_vector)
            if nearest_vectors:
                if percept_vector.name not in nearest_vectors:
                    nearest_vectors += [percept_vector.name]
                return list(set(nearest_vectors))
            else:
                return [percept_vector.name]