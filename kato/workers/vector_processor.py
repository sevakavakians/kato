import logging
from functools import reduce
from math import isfinite
from os import environ
from typing import Any

from numpy import array

from kato.config.session_config import (
    DEFAULT_VECTOR_EVENT_MODE,
    DEFAULT_VECTOR_SEARCH_LIMIT,
    MAX_VECTOR_SEARCH_LIMIT,
    VALID_VECTOR_EVENT_MODES,
    VECTOR_EVENT_MODE_SELF_ONLY,
)
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

    def process(
        self,
        vector_data,
        vector_event_mode=DEFAULT_VECTOR_EVENT_MODE,
        vector_search_limit=DEFAULT_VECTOR_SEARCH_LIMIT,
    ):
        symbols, _ = self._process(
            vector_data,
            vector_event_mode=vector_event_mode,
            vector_search_limit=vector_search_limit,
            include_search_results=False,
        )
        return symbols

    def process_with_diagnostics(
        self,
        vector_data,
        vector_event_mode=DEFAULT_VECTOR_EVENT_MODE,
        vector_search_limit=DEFAULT_VECTOR_SEARCH_LIMIT,
    ) -> tuple[list[str], dict[str, Any]]:
        """Process vectors and return request-local nearest-neighbor diagnostics."""
        return self._process(
            vector_data,
            vector_event_mode=vector_event_mode,
            vector_search_limit=vector_search_limit,
            include_search_results=True,
        )

    def _process(
        self,
        vector_data,
        *,
        vector_event_mode,
        vector_search_limit,
        include_search_results,
    ):
        if vector_event_mode not in VALID_VECTOR_EVENT_MODES:
            raise ValueError(f"Invalid vector_event_mode: {vector_event_mode}")
        if (isinstance(vector_search_limit, bool) or
                not isinstance(vector_search_limit, int) or
                not 1 <= vector_search_limit <= MAX_VECTOR_SEARCH_LIMIT):
            raise ValueError(f"Invalid vector_search_limit: {vector_search_limit}")

        logger.debug(vector_data)
        # Convert list of lists to numpy arrays
        vector_data = [array(v) for v in vector_data]
        logger.debug(vector_data)
        percept_vector = reduce(lambda x,y: x+y, vector_data)
        logger.debug(percept_vector)
        percept_vector = VectorObject(percept_vector)
        logger.debug(percept_vector)
        if self.indexer_type == "VI":
            if vector_event_mode == VECTOR_EVENT_MODE_SELF_ONLY:
                self.deferred_vectors_for_learning.append(percept_vector)
                diagnostics = self._build_diagnostics(
                    percept_vector,
                    vector_search_limit,
                    [],
                    search_performed=False,
                ) if include_search_results else None
                return [percept_vector.name], diagnostics

            search_results = None
            if include_search_results:
                search_results = self.vector_indexer.findNearestResults(
                    percept_vector,
                    k=vector_search_limit,
                )
                nearest_vectors = [str(result.id) for result in search_results]
            elif vector_search_limit == DEFAULT_VECTOR_SEARCH_LIMIT:
                # Keep the existing default call shape for compatibility.
                nearest_vectors = self.vector_indexer.findNearestPoints(percept_vector)
            else:
                nearest_vectors = self.vector_indexer.findNearestPoints(
                    percept_vector,
                    k=vector_search_limit,
                )

            self.deferred_vectors_for_learning.append(percept_vector)
            if nearest_vectors:
                if percept_vector.name not in nearest_vectors:
                    nearest_vectors += [percept_vector.name]
                symbols = list(set(nearest_vectors))
            else:
                symbols = [percept_vector.name]

            diagnostics = self._build_diagnostics(
                percept_vector,
                vector_search_limit,
                search_results or [],
                search_performed=True,
            ) if include_search_results else None
            return symbols, diagnostics

        return None, None

    def _build_diagnostics(
        self,
        percept_vector: VectorObject,
        vector_search_limit: int,
        search_results: list,
        *,
        search_performed: bool,
    ) -> dict[str, Any]:
        metric = self._vector_metric()
        matches = []
        seen_ids = set()

        for result in search_results:
            vctr_id = str(result.id)
            if vctr_id in seen_ids:
                continue
            seen_ids.add(vctr_id)
            raw_score = float(result.score)
            if not isfinite(raw_score):
                raise ValueError(f"Non-finite vector search score for {vctr_id}")
            matches.append({
                'vctr_id': vctr_id,
                'rank': len(matches) + 1,
                'raw_score': raw_score,
                'source': 'vector_index',
            })

        if search_performed and percept_vector.name not in seen_ids:
            matches.append({
                'vctr_id': percept_vector.name,
                'rank': len(matches) + 1,
                'raw_score': None,
                'source': 'self_appended',
            })

        return {
            'query_vctr_id': percept_vector.name,
            'requested_limit': vector_search_limit,
            'search_performed': search_performed,
            'metric': metric,
            'score_direction': self._score_direction(metric),
            'matches': matches,
        }

    def _vector_metric(self) -> str:
        engine = getattr(self.vector_indexer, 'engine', None)
        config = getattr(engine, 'config', None)
        return str(getattr(config, 'similarity_metric', 'unknown'))

    @staticmethod
    def _score_direction(metric: str) -> str:
        if metric in {'euclidean', 'manhattan'}:
            return 'lower_is_better'
        if metric in {'cosine', 'dot'}:
            return 'higher_is_better'
        return 'unknown'
