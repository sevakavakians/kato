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
from kato.representations.model import Model
from kato.searches.model_search import ModelSearcher

from collections import Counter

logger = logging.getLogger('kato.modeler')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')

class Modeler:
    """
    Responsible for creating new, recognizing known, discovering unknown, and predicting models.
    """
    def __init__(self, **kwargs):
        logger.debug("Starting Modeler...")
        logger.debug(f"Modeler kwargs: {kwargs}")
        self.name = f"{kwargs['name']}-Modeler"
        self.kb_id = kwargs["kb_id"] # Use this to connect to the KB.
        self.max_sequence_length = kwargs["max_sequence_length"]
        self.persistence = kwargs["persistence"]
        self.smoothness = kwargs["smoothness"]
        self.AUTOACT_METHOD = kwargs["auto_act_method"]
        self.AUTOACT_THRESHOLD = kwargs["auto_act_threshold"]
        self.always_update_frequencies = kwargs["always_update_frequencies"]
        self.max_predictions = int(kwargs["max_predictions"])
        self.recall_threshold = float(kwargs["recall_threshold"])
        self.QUIESCENCE = kwargs["quiescence"]
        self.superkb = SuperKnowledgeBase(self.kb_id, self.persistence)
        self.models_searcher = ModelSearcher(kb_id=self.kb_id,
                                             max_predictions=self.max_predictions,
                                             recall_threshold=self.recall_threshold)
        self.initiateDefaults()
        self.predict = True
        self.predictions_kb = self.superkb.predictions_kb
        self.mood = {}
        self.target_class = None
        self.target_class_candidates = []
        logger.info(f"Modeler {self.name} started!")
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
        self.last_learned_model_name = None
        self.models_searcher.clearModelsFromRAM()
        self.superkb.models_observation_count = 0
        self.superkb.symbols_observation_count = 0
        self.initiateDefaults()
        return

    def initiateDefaults(self):
        self.QUIESCENCE_COUNT = 0
        self.STM = deque()
        self.emotives = []
        self.mood = {}
        self.last_learned_model_name = None
        self.models_searcher.getModels()
        self.trigger_predictions = False
        return

    def learn(self):
        """
        Convert current short-term memory into a persistent model.
        
        Creates a hash-named model from the sequence in STM, stores it in MongoDB,
        and distributes it to search workers for future pattern matching.
        """
        model = Model(self.STM)  # Create model from short-term memory sequence
        self.STM.clear()  # Reset short-term memory after learning
        
        if len(model) > 1:  # Only learn multi-event sequences
            # Store model with averaged emotives from all events
            x = self.models_kb.learnModel(model, emotives=average_emotives(self.emotives))
            
            if x:
                # Add newly learned model to the searcher
                # Index parameter kept for backward compatibility but ignored by optimized version
                self.models_searcher.assignNewlyLearnedToWorkers(
                    0,  # Index parameter ignored in optimized implementation
                    model.name, 
                    list(chain(*model.sequence))
                )
            self.last_learned_model_name = model.name
            del(model)
            self.emotives = []
            return self.last_learned_model_name
        self.emotives = []
        return None

    def delete_model(self, name):
        if not self.models_searcher.delete_model(name):
            raise Exception(f'Unable to find and delete model {name} in RAM')
        result = self.models_kb.delete_one({"name": name})
        if result.deleted_count != 1:
            logger.warning(f'Expected to delete 1 record for model {name} but deleted {result.deleted_count}')
        return 'deleted'

    def update_model(self, name, frequency, emotives):
        """Return the updated version of the model *name* with new frequency and emotives set."""
        for emotive, values_list in emotives.items():
            if len(values_list) > self.persistence:
                raise Exception(f'{emotive} array length ({len(values_list)}) exceeds system persistence ({self.persistence})')
        return self.models_kb.find_one_and_update(
            {'name': name},
            {'$set': {'frequency': frequency, 'emotives': emotives}},
            {'_id': False},
            return_document=ReturnDocument.AFTER
        )

    def processEvents(self, current_unique_id):
        """
        Generate predictions by matching short-term memory against learned models.
        
        Flattens the STM (list of events) into a single state vector,
        then searches for similar patterns in the model database.
        Predictions are cached in MongoDB for retrieval.
        
        Note: KATO requires at least 2 strings in STM to generate predictions.
        """
        # Flatten short-term memory: [["a","b"],["c"]] -> ["a","b","c"]
        state = list(chain(*self.STM))
        
        # Only generate predictions if we have at least 2 strings in state
        # KATO requires minimum 2 strings for pattern matching
        if len(state) >= 2 and self.predict and self.trigger_predictions:
            predictions = self.predictModel(state)
            
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

    def symbolProbability(self, symbol, total_symbols_in_models_frequencies):
        "Grab symbol frequency from symbols_kb. Test 'model_member_frequency' or 'frequency'."
        # We can either look at using the probability of a symbol to appear anywhere in the KB, which means it can also appear
        # multiple times in one sequence, or we can look at the probability of a symbol to appear in any sequence, regardless
        # of the number of times it appears within any one sequence.
        # We can also look at coming up with a formula to account for both to affect the potential.
        return float(self.superkb.symbols_kb.find_one({"name": symbol})['model_member_frequency']/total_symbols_in_models_frequencies) ## or ['frequency']

    def modelProbability(self, freq, total_model_frequencies):
        return float(freq/total_model_frequencies)

    def predictModel(self, state):
        "Predict models and update active model fractional frequencies considering the inverse frequency values of the symbols."
        logger.debug(f" {self.name} [ Modeler predictModel called ]")
        total_symbols = self.superkb.symbols_kb.count_documents({})
        total_symbols_in_models_frequencies = self.superkb.metadata.find_one(
            {"class": "totals"})['total_symbols_in_models_frequencies']
        total_model_frequencies = self.superkb.metadata.find_one({"class": "totals"})['total_model_frequencies']
        try:
            causal_models = self.models_searcher.causalBelief(state, self.target_class_candidates)
        except Exception as e:
            raise Exception("\nException in Modeler.predictModel: Error in causalBelief! %s: %s" %(self.kb_id, e))
        
        try:
            # Fetch and pre-calculate the probability (for the union of symbols in matches and missing) exactly once, to
            # be used in the calculations that follow
            symbol_probability_cache = {}
            symbol_frequency_cache = Counter()
            total_ensemble_model_frequencies = 0
            symbol_cache = {}
            all_symbols = self.superkb.symbols_kb.find({}, {'_id': False}, cursor_type=pymongo.CursorType.EXHAUST)
            for symbol in all_symbols:
                symbol_cache[symbol['name']] = symbol
            for prediction in causal_models:
                total_ensemble_model_frequencies += prediction['frequency']
                for symbol in itertools.chain(prediction['matches'], prediction['missing']):
                    if symbol not in symbol_probability_cache or symbol not in symbol_frequency_cache:
                        # Check if symbol exists in cache, skip if not (new/unknown symbol)
                        if symbol not in symbol_cache:
                            symbol_probability_cache[symbol] = 0
                            symbol_frequency_cache[symbol] = 0
                            continue
                        symbol_data = symbol_cache[symbol]
                        symbol_probability = float(symbol_data['model_member_frequency'] / total_symbols_in_models_frequencies)
                        symbol_probability_cache[symbol] = symbol_probability
                        symbol_frequency_cache[symbol] += symbol_data['frequency']
            symbol_frequency_in_state = Counter(state)
            # We need to account for new symbols that appear in state that have never been observed before, therefore would fail on key error in symbol_probability_cache.
            for symbol in symbol_frequency_in_state.keys():
                if symbol not in symbol_frequency_cache:
                    symbol_frequency_cache[symbol] = 0
            for prediction in causal_models:
                _present = list(chain(*prediction.present)) #list(chain(*prediction['present']))
                all_symbols = set(_present + state)
                symbol_frequency_in_model = Counter(_present)
                state_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_state.get(symbol, 0)) for symbol in all_symbols]
                model_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_model.get(symbol, 0)) for symbol in all_symbols]
                _p_e_h = float(self.modelProbability(prediction['frequency'], total_model_frequencies)) # p(e|h)
                distance = float(spatial.distance.cosine(state_frequency_vector, model_frequency_vector))
                itfdf_similarity = round(float(1 - (distance * prediction['frequency'] / total_ensemble_model_frequencies)), 12)
                prediction['itfdf_similarity'] = itfdf_similarity
                prediction['entropy'] = round(float(sum([classic_expectation(symbol_probability_cache.get(symbol, 0)) for symbol in _present])), 12)
                prediction['hamiltonian'] = round(float(hamiltonian(_present, total_symbols)), 12)
                prediction['grand_hamiltonian'] = round(float(grand_hamiltonian(_present, symbol_probability_cache, total_symbols)), 12)
                prediction['confluence'] = round(float(_p_e_h * (1 - conditionalProbability(_present, symbol_probability_cache) ) ), 12) # = probability of sequence occurring in observations * ( 1 - probability of sequence occurring randomly)
                prediction['potential'] = round(float( ( prediction['evidence'] + prediction['confidence'] ) * prediction.get("snr", 0) + prediction['itfdf_similarity'] + (1/ (prediction['fragmentation'] +1) ) ), 12)
                prediction['emotives'] = average_emotives(prediction['emotives'])
                prediction.pop('sequence')

        except Exception as e:
            raise Exception("\nException in Modeler.predictModel: Error in potential calculation! %s: %s" %(self.kb_id, e))
        try:
            active_causal_models = sorted([x for x in heapq.nlargest(self.max_predictions,causal_models,key=itemgetter('potential'))], reverse=True, key=itemgetter('potential'))
        except Exception as e:
            raise Exception("\nException in Modeler.predictModel: Error in sorting predictions! %s: %s" %(self.kb_id, e))
        logger.debug(" [ Modeler predictModel ] %s active_causal_models" %(len(active_causal_models)))
        return active_causal_models
