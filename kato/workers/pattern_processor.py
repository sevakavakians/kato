import heapq
import itertools
import logging
from os import environ
from collections import deque
from itertools import chain
from operator import itemgetter

import pymongo
from scipy import spatial
from pymongo import ReturnDocument

from kato.informatics.knowledge_base import SuperKnowledgeBase
from kato.informatics.metrics import average_emotives, \
                                            classic_expectation, \
                                            grand_hamiltonian, \
                                            hamiltonian, \
                                            conditionalProbability, \
                                            confluence, \
                                            expectation
from kato.representations.pattern import Pattern
from kato.searches.pattern_search import PatternSearcher

from collections import Counter

logger = logging.getLogger('kato.pattern_processor')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')

class PatternProcessor:
    """
    Responsible for creating new, recognizing known, discovering unknown, and predicting patterns.
    Patterns can be temporal (sequences) or non-temporal (profiles).
    """
    def __init__(self, **kwargs):
        logger.debug("Starting PatternProcessor...")
        logger.debug(f"PatternProcessor kwargs: {kwargs}")
        self.name = f"{kwargs['name']}-PatternProcessor"
        self.kb_id = kwargs["kb_id"] # Use this to connect to the KB.
        self.max_pattern_length = kwargs["max_pattern_length"]
        self.persistence = kwargs["persistence"]
        self.smoothness = kwargs["smoothness"]
        self.AUTOACT_METHOD = kwargs["auto_act_method"]
        self.AUTOACT_THRESHOLD = kwargs["auto_act_threshold"]
        self.always_update_frequencies = kwargs["always_update_frequencies"]
        self.max_predictions = int(kwargs["max_predictions"])
        self.recall_threshold = float(kwargs["recall_threshold"])
        self.QUIESCENCE = kwargs["quiescence"]
        self.superkb = SuperKnowledgeBase(self.kb_id, self.persistence)
        self.patterns_searcher = PatternSearcher(kb_id=self.kb_id,
                                             max_predictions=self.max_predictions,
                                             recall_threshold=self.recall_threshold)
        self.initiateDefaults()
        self.predict = True
        self.predictions_kb = self.superkb.predictions_kb
        self.mood = {}
        self.target_class = None
        self.target_class_candidates = []
        logger.info(f"PatternProcessor {self.name} started!")
        return

    def setSTM(self, x):
        self.STM = deque(x)
        return

    def clear_stm(self):
        self.STM = deque()
        self.trigger_predictions = False
        self.emotives = []
        return

    def clear_all_memory(self):
        self.clear_stm()
        self.last_learned_pattern_name = None
        self.patterns_searcher.clearPatternsFromRAM()
        self.superkb.patterns_observation_count = 0
        self.superkb.symbols_observation_count = 0
        self.initiateDefaults()
        return

    def initiateDefaults(self):
        self.QUIESCENCE_COUNT = 0
        self.STM = deque()
        self.emotives = []
        self.mood = {}
        self.last_learned_pattern_name = None
        self.patterns_searcher.getPatterns()
        self.trigger_predictions = False
        return

    def learn(self):
        """
        Convert current short-term memory into a persistent pattern.
        
        Creates a hash-named pattern from the data in STM, stores it in MongoDB,
        and distributes it to search workers for future pattern matching.
        """
        pattern = Pattern(self.STM)  # Create pattern from short-term memory data
        self.STM.clear()  # Reset short-term memory after learning
        
        if len(pattern) > 1:  # Only learn multi-event patterns
            # Store pattern with averaged emotives from all events
            x = self.patterns_kb.learnPattern(pattern, emotives=average_emotives(self.emotives))
            
            if x:
                # Add newly learned pattern to the searcher
                # Index parameter kept for backward compatibility but ignored by optimized version
                self.patterns_searcher.assignNewlyLearnedToWorkers(
                    0,  # Index parameter ignored in optimized implementation
                    pattern.name, 
                    list(chain(*pattern.pattern_data))
                )
            self.last_learned_pattern_name = pattern.name
            del(pattern)
            self.emotives = []
            return self.last_learned_pattern_name
        self.emotives = []
        return None

    def delete_pattern(self, name):
        if not self.patterns_searcher.delete_pattern(name):
            raise Exception(f'Unable to find and delete pattern {name} in RAM')
        result = self.patterns_kb.delete_one({"name": name})
        if result.deleted_count != 1:
            logger.warning(f'Expected to delete 1 record for pattern {name} but deleted {result.deleted_count}')
        return 'deleted'

    def update_pattern(self, name, frequency, emotives):
        """Return the updated version of the pattern *name* with new frequency and emotives set."""
        for emotive, values_list in emotives.items():
            if len(values_list) > self.persistence:
                raise Exception(f'{emotive} array length ({len(values_list)}) exceeds system persistence ({self.persistence})')
        return self.patterns_kb.find_one_and_update(
            {'name': name},
            {'$set': {'frequency': frequency, 'emotives': emotives}},
            {'_id': False},
            return_document=ReturnDocument.AFTER
        )

    def processEvents(self, current_unique_id):
        """
        Generate predictions by matching short-term memory against learned patterns.
        
        Flattens the STM (list of events) into a single state vector,
        then searches for similar patterns in the pattern database.
        Predictions are cached in MongoDB for retrieval.
        
        Note: KATO requires at least 2 strings in STM to generate predictions.
        """
        # Flatten short-term memory: [["a","b"],["c"]] -> ["a","b","c"]
        state = list(chain(*self.STM))
        
        # Only generate predictions if we have at least 2 strings in state
        # KATO requires minimum 2 strings for pattern matching
        if len(state) >= 2 and self.predict and self.trigger_predictions:
            predictions = self.predictPattern(state)
            
            # Store predictions for async retrieval
            if predictions:
                self.predictions_kb.insert_one({
                    'unique_id': current_unique_id, 
                    'predictions': predictions
                })
            return predictions
        
        # Return empty predictions if state is too short
        return []

    def setCurrentEvent(self, symbols):
        """
        Add a new event (list of symbols) to short-term memory.
        
        Short-term memory is a deque of events, where each event is a list of symbols
        observed at the same time. E.g., STM = [["cat","dog"], ["bird"], ["cat"]]
        """
        if symbols:
            self.STM.append(symbols)
        return
    
    def symbolFrequency(self, symbol):
        return self.superkb.symbols_kb.find_one({"name": symbol})['frequency']

    def symbolProbability(self, symbol, total_symbols_in_patterns_frequencies):
        "Grab symbol frequency from symbols_kb. Test 'pattern_member_frequency' or 'frequency'."
        # We can either look at using the probability of a symbol to appear anywhere in the KB, which means it can also appear
        # multiple times in one pattern, or we can look at the probability of a symbol to appear in any pattern, regardless
        # of the number of times it appears within any one pattern.
        # We can also look at coming up with a formula to account for both to affect the potential.
        return float(self.superkb.symbols_kb.find_one({"name": symbol})['pattern_member_frequency']/total_symbols_in_patterns_frequencies) if total_symbols_in_patterns_frequencies > 0 else 0.0 ## or ['frequency']

    def patternProbability(self, freq, total_pattern_frequencies):
        return float(freq/total_pattern_frequencies) if total_pattern_frequencies > 0 else 0.0

    def predictPattern(self, state):
        "Predict patterns and update active pattern fractional frequencies considering the inverse frequency values of the symbols."
        logger.debug(f" {self.name} [ PatternProcessor predictPattern called ]")
        total_symbols = self.superkb.symbols_kb.count_documents({})
        total_symbols_in_patterns_frequencies = self.superkb.metadata.find_one(
            {"class": "totals"})['total_symbols_in_patterns_frequencies']
        total_pattern_frequencies = self.superkb.metadata.find_one({"class": "totals"})['total_pattern_frequencies']
        try:
            causal_patterns = self.patterns_searcher.causalBelief(state, self.target_class_candidates)
        except Exception as e:
            raise Exception("\nException in PatternProcessor.predictPattern: Error in causalBelief! %s: %s" %(self.kb_id, e))
        
        try:
            # Fetch and pre-calculate the probability (for the union of symbols in matches and missing) exactly once, to
            # be used in the calculations that follow
            symbol_probability_cache = {}
            symbol_frequency_cache = Counter()
            total_ensemble_pattern_frequencies = 0
            symbol_cache = {}
            all_symbols = self.superkb.symbols_kb.find({}, {'_id': False}, cursor_type=pymongo.CursorType.EXHAUST)
            for symbol in all_symbols:
                symbol_cache[symbol['name']] = symbol
            for prediction in causal_patterns:
                total_ensemble_pattern_frequencies += prediction['frequency']
                for symbol in itertools.chain(prediction['matches'], prediction['missing']):
                    if symbol not in symbol_probability_cache or symbol not in symbol_frequency_cache:
                        # Check if symbol exists in cache, skip if not (new/unknown symbol)
                        if symbol not in symbol_cache:
                            symbol_probability_cache[symbol] = 0
                            symbol_frequency_cache[symbol] = 0
                            continue
                        symbol_data = symbol_cache[symbol]
                        symbol_probability = float(symbol_data['pattern_member_frequency'] / total_symbols_in_patterns_frequencies) if total_symbols_in_patterns_frequencies > 0 else 0.0
                        symbol_probability_cache[symbol] = symbol_probability
                        symbol_frequency_cache[symbol] += symbol_data['frequency']
            symbol_frequency_in_state = Counter(state)
            # We need to account for new symbols that appear in state that have never been observed before, therefore would fail on key error in symbol_probability_cache.
            for symbol in symbol_frequency_in_state.keys():
                if symbol not in symbol_frequency_cache:
                    symbol_frequency_cache[symbol] = 0
            for prediction in causal_patterns:
                _present = list(chain(*prediction.present)) #list(chain(*prediction['present']))
                all_symbols = set(_present + state)
                symbol_frequency_in_pattern = Counter(_present)
                state_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_state.get(symbol, 0)) for symbol in all_symbols]
                pattern_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_pattern.get(symbol, 0)) for symbol in all_symbols]
                _p_e_h = float(self.patternProbability(prediction['frequency'], total_pattern_frequencies)) # p(e|h)
                distance = float(spatial.distance.cosine(state_frequency_vector, pattern_frequency_vector))
                itfdf_similarity = round(float(1 - (distance * prediction['frequency'] / total_ensemble_pattern_frequencies)) if total_ensemble_pattern_frequencies > 0 else 0.0, 12)
                prediction['itfdf_similarity'] = itfdf_similarity
                prediction['entropy'] = round(float(sum([classic_expectation(symbol_probability_cache.get(symbol, 0)) for symbol in _present])), 12)
                prediction['hamiltonian'] = round(float(hamiltonian(_present, total_symbols)), 12)
                prediction['grand_hamiltonian'] = round(float(grand_hamiltonian(_present, symbol_probability_cache, total_symbols)), 12)
                prediction['confluence'] = round(float(_p_e_h * (1 - conditionalProbability(_present, symbol_probability_cache) ) ), 12) # = probability of sequence occurring in observations * ( 1 - probability of sequence occurring randomly)
                prediction['potential'] = round(float( ( prediction['evidence'] + prediction['confidence'] ) * prediction.get("snr", 0) + prediction['itfdf_similarity'] + (1/ (prediction['fragmentation'] +1) ) ), 12)
                prediction['emotives'] = average_emotives(prediction['emotives'])
                prediction.pop('pattern_data')

        except Exception as e:
            raise Exception("\nException in PatternProcessor.predictPattern: Error in potential calculation! %s: %s" %(self.kb_id, e))
        try:
            active_causal_patterns = sorted([x for x in heapq.nlargest(self.max_predictions,causal_patterns,key=itemgetter('potential'))], reverse=True, key=itemgetter('potential'))
        except Exception as e:
            raise Exception("\nException in PatternProcessor.predictPattern: Error in sorting predictions! %s: %s" %(self.kb_id, e))
        logger.debug(" [ PatternProcessor predictPattern ] %s active_causal_patterns" %(len(active_causal_patterns)))
        return active_causal_patterns
