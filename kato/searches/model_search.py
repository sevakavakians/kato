import logging
from os import environ
import heapq
import multiprocessing
from collections import Counter
from itertools import chain
from operator import itemgetter
from queue import Queue

from pymongo import MongoClient

from kato.informatics import extractor as difflib
from kato.representations.prediction import Prediction

logger = logging.getLogger('kato.searches.model_search')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')

class InformationExtractorWorker(multiprocessing.Process):
    def __init__(self, datasubset, result_queue):
        super(InformationExtractorWorker, self).__init__()
        logger.debug('logging initiated')
        try:
            self.datasubset = datasubset
            self.state = None
            self.cutoff = None
            self.target_class_candidates = []
            self.results = result_queue
        except Exception as e:
            raise Exception("\nException in InformationExtractorWorker: Failed to create Worker! %s" %e)

    def run(self):
        pass

    def InformationExtractorWorkerGo(self):
        """
        Extract prediction information by comparing current state to stored models.
        
        Uses difflib's SequenceMatcher to find similar sequences and extract:
        - Past: what happened before the match
        - Present: the matching portion
        - Future: what's predicted to come next
        - Missing/Extra: anomalies in the current observation
        """
        try:
            if self.state and self.datasubset:
                # Create sequence matcher for comparing models to current state
                model_matcher = difflib.SequenceMatcher()
                model_matcher.set_seq2(self.state)  # Current observation state
                
                # Check each model in this worker's subset
                for model_hash, model in self.datasubset.items():
                    if self.target_class_candidates:
                        if model_hash not in self.target_class_candidates:
                            continue
                    # logger.debug("MODEL: %s " %(model[:5]))
                    try:
                        model_matcher.set_seq1(model)
                        similarity = model_matcher.ratio()
                    except Exception as e:
                        logger.error("\nException in InformationExtractorWorker: Failed to create Sequence Match! %s" %e)
                        raise Exception("\nException in InformationExtractorWorker: Failed to create Sequence Match! %s" %e)
                    if similarity >= self.cutoff:
                        # Extract temporal structure from the match
                        try:
                            matching_intersection = []  # Symbols that match between model and state
                            matching_blocks = model_matcher.get_matching_blocks()

                            # Collect all matching symbols
                            for block in matching_blocks[:-1]:  # Skip terminator block
                                (i,j,n) = tuple(block)  # (model_idx, state_idx, length)
                                matching_intersection += self.state[j:j+n]

                            matching_count = sum([x[2] for x in matching_blocks])

                            # Extract temporal regions from the model
                            (i0,j0,n0) = tuple(matching_blocks[0])  # First match
                            (i1,j1,n1) = tuple(matching_blocks[-2])  # Last real match
                            
                            # Past: symbols before first match (context)
                            past = model[:i0]
                            # Present: symbols from first to last match (current state)
                            present = model[i0:i1+n1]
                            # Future would be: model[i1+n1:] (what comes next)
                            
                            number_of_blocks = len(matching_blocks)-1
                            #present_in_state = self.state[j0:j1+n1] ##not used
                            #future = model[i1+n1:]
                        except Exception as e:
                            logger.error("\nException in InformationExtractorWorker: Failed to extract PRESENT belief! %s" %e)
                            raise Exception("\nException in InformationExtractorWorker: Failed to extract PRESENT belief! %s" %e)

                        # Identify anomalies: what's missing or extra in current observation
                        try:
                            missing = []  # Expected symbols not present
                            extras = []   # Unexpected symbols present
                            
                            # Compare present portion of model to actual state
                            model_matcher.set_seq1(present)
                            model_matcher.get_matching_blocks()
                            diffs = model_matcher.compare()
                            diffs = list(diffs)
                            
                            # Parse diff output
                            for i in diffs:
                                if i.startswith("- "):  # In model but not in state
                                    missing.append(i[2:])
                                elif i.startswith("+ "):  # In state but not in model
                                    extras.append(i[2:])
                        except Exception as e:
                            logger.error("\nException in InformationExtractorWorker: Failed in extracting ANOMALIES belief! %s" %e)
                            raise Exception("\nException in InformationExtractorWorker: Failed in extracting ANOMALIES belief! %s" %e)
                        x = model_hash, model, matching_intersection, past, present, missing, extras, similarity, number_of_blocks
                        self.results.put(x)
        except Exception as e:
            logger.error("\nException in InformationExtractorWorker.go: %s" %e)
            raise Exception("\nException in InformationExtractorWorker.go: %s" %e)
        self.results.put(None)  ## Poison pill to signal end of queue.
        return

class PredictionBuilder(multiprocessing.Process):
    def __init__(self, datasubset, result_queue, kb_id):
        super(PredictionBuilder, self).__init__()
        logger.debug('logging initiated')
        try:
            self.connection = MongoClient('%s' %environ['MONGO_BASE_URL'])
            self.knowledgebase = self.connection[kb_id]
            self.datasubset = datasubset
            self.results = result_queue
        except Exception as e:
            raise Exception("\nException in PredictionBuilder!: %s" %(e))

    def run(self):
        pass

    def close(self):
        self.connection.close()
        return

    def PredictionBuilderGo(self):
        try:
            if self.datasubset:
                for model_hash, model, matching_intersection, past, present, missing, extras, similarity, number_of_blocks in self.datasubset:
                    try:
                        x = Prediction(self.knowledgebase.models_kb.find_one({"name": model_hash}, {"_id": 0}),
                                    matching_intersection,
                                    past, present,
                                    missing,
                                    extras,
                                    similarity,
                                    number_of_blocks
                                    )
                    except Exception as e:
                        raise Exception("\nException in PredictionBuilder: Failed in building PREDICTION object! %s" %e)
                    self.results.put(x)
        except Exception as e:
            raise Exception("\nException in PredictionBuilder.go: %s" %e)
        self.results.put(None)
        return

class ModelSearcher:
    def __init__(self, **kwargs):
        try:
            self.procs = multiprocessing.cpu_count()
            logger.info(" ** Found %s CPUs!" %self.procs)
            self.kb_id = kwargs["kb_id"]
            self.connection = MongoClient('%s' %environ['MONGO_BASE_URL'])
            logger.debug(f"ModelSearch mongo connection id {self.kb_id}")
            self.knowledgebase = self.connection[self.kb_id]
            self.max_predictions = kwargs["max_predictions"]
            self.recall_threshold = kwargs["recall_threshold"]
            self.models_count = 0
            self.extractions_queue = Queue()
            self.extraction_workers = [InformationExtractorWorker({}, self.extractions_queue) for proc in range(self.procs)]
            [worker.start() for worker in self.extraction_workers]
            self.predictions_queue = Queue()
            self.prediction_workers = [PredictionBuilder([], self.predictions_queue, self.kb_id) for proc in range(self.procs)]
            [worker.start() for worker in self.prediction_workers]
        except Exception as e:
            raise Exception("\nException initializing ModelSearcher! %s" %e)

    def delete_model(self, name):
        """Return True if we were able to find and delete the model from RAM."""
        for worker in self.extraction_workers:
            if name in worker.datasubset:
                del worker.datasubset[name]
                logger.debug(f'Successfully deleted model {name} from RAM')
                return True
        return False

    def clearModelsFromRAM(self):
        self.models_count = 0
        [(setattr(worker, "state", []), setattr(worker, "datasubset", {})) for worker in self.extraction_workers]
        [(setattr(worker, "datasubset", [])) for worker in self.prediction_workers]
        return


    def getModels(self):
        connection = MongoClient('%s' %environ['MONGO_BASE_URL'])
        _models = {}
        for m in self.knowledgebase.models_kb.find({}, {"name": 1, "sequence": 1}):
            _models[m["name"]] = list(chain(*m["sequence"]))
        self.models_count = self.knowledgebase.models_kb.count_documents({}) #len(_models)
        if _models:
            logger.debug("  ModelSearch found %s existing models!" %(self.models_count))
            models_per_worker = max(int(round(len(_models)/len(self.extraction_workers))), 1)
            for worker in self.extraction_workers:
                for _ in range(models_per_worker):
                    if not _models:
                        break
                    key, value = _models.popitem()
                    worker.datasubset[key] = value
            while _models:
                key, value = _models.popitem()
                self.extraction_workers[0].datasubset[key] = value

    def dataAssignments(self, dataset, workers):
        L = max(int(round(len(dataset)/len(workers))), 1)
        m, n = 0, L
        for worker in workers:
            worker.datasubset = dataset[m:n]
            m, n = n, n + L + 1
        return

    def assignNewlyLearnedToWorkers(self, index, model_name, new_model):
        "Assigning newly learned to workers so that we don't re-assign from scratch every time."
        self.models_count += 1
        self.extraction_workers[index].datasubset[model_name] = new_model
        return

    def causalBelief(self, state, target_class_candidates=[]):
        "Determines the sequential belief and returns Predictions."

        if (self.models_count == 0):
            self.getModels()

        ## Pattern match and extract info:
        try:
            [(setattr(worker, "state", state), setattr(worker, "cutoff", self.recall_threshold), setattr(worker, "target_class_candidates", target_class_candidates)) for worker in self.extraction_workers]
            [worker.InformationExtractorWorkerGo() for worker in self.extraction_workers]
            [worker.join() for worker in self.extraction_workers]
        except Exception as e:
            logger.error("\nException in ModelSearch.causalBelief: Trouble setting prediction workers! %s" %e)
            raise Exception("\nException in ModelSearch.causalBelief: Trouble setting prediction workers! %s" %e)

        results = []
        finished_counter = 0
        while finished_counter != len(self.extraction_workers):
            if self.extractions_queue.empty() == False:
                r = self.extractions_queue.get()
                if r is not None:
                    results.append(r)
                else:
                    finished_counter += 1

        logger.debug("  ModelSearch returning %s active_results" %(len(results)))

        ## Create Prediction objects of results:
        if not results:
            return []
        try:
            self.dataAssignments(results, self.prediction_workers)
            [worker.PredictionBuilderGo() for worker in self.prediction_workers]
            [worker.join() for worker in self.prediction_workers]

            active_list = []
            finished_counter = 0
            while finished_counter != len(self.prediction_workers):
                if self.predictions_queue.empty() == False:
                    r = self.predictions_queue.get()
                    if r is not None:
                        active_list.append(r)
                    else:
                        finished_counter += 1
        except Exception as e:
            logger.error("\nException in ModelSearch.causalBelief: Trouble separating beliefs! %s" %e)
            raise Exception("\nException in ModelSearch.causalBelief: Trouble separating beliefs! %s" %e)

        logger.debug("  ModelSearch returning %s active_list" %(len(active_list)))
        
        return active_list

    def __del__(self):
        [worker.terminate() for worker in self.extraction_workers]
        [worker.close() for worker in self.prediction_workers]  ##Closes the MongoDB connection.
        [worker.terminate() for worker in self.prediction_workers]
        self.connection.close()
        return
