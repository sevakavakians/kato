import logging
from os import environ
from functools import reduce

from numpy import array

from kato.informatics.knowledge_base import SuperKnowledgeBase  # , KnowledgeBase
from kato.representations.vector_object import VectorObject
from kato.searches import vector_searches
from kato.searches.vector_search_engine import CVCSearcherModern

logger = logging.getLogger('kato.classifier')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


class Classifier:
    """
    Processes percept VectorObjects to determine the object representations.
    Multiple classifiers are available including:
        Canonical Vector (via Canonical Vector Pursuit)
        Hyperspheres/Hyperblobs  (via generalized SVM)
        more to be added.
    """
    def __init__(self, procs_for_searches, **kwargs):
        logger.debug("Starting Classifier...")
        self.name = "Classifier"
        self.kb_id = kwargs["kb_id"]
        self.classifier = kwargs["classifier"]
        self.search_depth = kwargs["search_depth"]
        self.primers = []
        self.procs_for_searches = procs_for_searches
        self.initializeVectorKBs()
        self.deferred_vectors_for_learning = []
        logger.debug("Classifier ready!")
        return

    def clear_all_memory(self):
        logger.debug("In Classifier clear all memory")
        self.deferred_vectors_for_learning = []
        if self.classifier == "CVC":
            self.CVC_searcher.clearModelsFromRAM()
            self.round_robin_index = 0
            logger.debug("about to reset CVCSearcher")
            self.CVC_searcher = CVCSearcherModern(self.procs_for_searches, self.vectors_kb)
        return

    def clear_wm(self):
        self.deferred_vectors_for_learning = []
        return

    def learn(self):
        [self.vectors_kb.learnVector(vector) for vector in self.deferred_vectors_for_learning]
        if self.classifier == "CVC":
            self.CVC_searcher.assignNewlyLearnedToWorkers(self.deferred_vectors_for_learning)
        self.deferred_vectors_for_learning = []
        return

    def initializeVectorKBs(self):
        self.superkb = SuperKnowledgeBase(self.kb_id)
        self.vectors_kb =  self.superkb.vectors_kb
        if self.classifier == "CVC":
            ### grab from mongo and populate using assignToWorkers
            self.round_robin_index = 0
            self.CVC_searcher = CVCSearcherModern(self.procs_for_searches, self.vectors_kb)
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
        if self.classifier == "DVC":
            if not percept_vector.isNull():
                recognized_objects, _discovered_object = vector_searches.vectorSearch(percept_vector, list(self.vectors_kb.values()), self.search_depth, self.primers)
                recognized_symbols = []
                if recognized_objects:
                    for vector in recognized_objects:
                        self.deferred_vectors_for_learning.append(vector)
                        recognized_symbols.append(vector.name)
                # If no objects were recognized (e.g., empty KB), use the percept vector itself
                if not recognized_symbols:
                    self.deferred_vectors_for_learning.append(percept_vector)
                    recognized_symbols = [percept_vector.name]
                return recognized_symbols
            else:
                self.deferred_vectors_for_learning.append(percept_vector)
                return [percept_vector.name]

        elif self.classifier == "CVC":
            nearest_vectors = self.CVC_searcher.findNearestPoints(percept_vector)
            self.deferred_vectors_for_learning.append(percept_vector)
            if nearest_vectors:
                if percept_vector.name not in nearest_vectors:
                    nearest_vectors += [percept_vector.name]
                return list(set(nearest_vectors))
            else:
                return [percept_vector.name]
