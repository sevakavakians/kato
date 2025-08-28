# cimport cython
import logging
from os import environ
import traceback
from typing import Counter
from multiprocessing import cpu_count, Lock

from kato.workers.vector_processor import VectorProcessor
from kato.workers.modeler import Modeler
from kato.informatics.metrics import average_emotives




logger = logging.getLogger('kato.workers.kato-processor')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


class KatoProcessor:
    def __init__(self, genome_manifest, **kwargs):
        '''genome is the specific kato processor's genes.'''
        self.genome_manifest = genome_manifest
        self.id = self.genome_manifest['id']
        self.name = self.genome_manifest["name"]
        self.vector_indexer_type = self.genome_manifest["indexer_type"]
        self.agent_name = environ['HOSTNAME']
        logger.info(" Starting KatoProcessor ID: %s" %self.id)

        self.SORT = self.genome_manifest["sort"]
        self.time = 0

        # Use all available processors now that we're using ZMQ instead of gRPC
        self.procs_for_searches = int(cpu_count())

        self.genome_manifest["kb_id"] = self.id
        self.vector_processor = VectorProcessor(self.procs_for_searches, **self.genome_manifest)
        self.modeler = Modeler(**self.genome_manifest)
        self.knowledge = self.modeler.superkb.knowledge
        self.modeler.models_kb = self.modeler.superkb.models_kb
        self.predictions_kb = self.knowledge.predictions_kb

        self.processing_lock = Lock()

        self.__primitive_variables_reset__()

        self.predictions = []
        logger.info(f" {self.name}-{self.id} kato processor, ready!")
        return

    def __primitive_variables_reset__(self):
        self.symbols = []
        self.current_emotives = {}
        self.last_command = ""
        self.modeler.v_identified = []
        self.percept_data = {}
        self.percept_data_vector = None
        return

    def _process_vectors_(self, vector_data):
        symbols = self.vector_processor.process(vector_data)
        return symbols

    def _process_emotives_(self, emotives):
        self.modeler.emotives += [emotives]
        self.current_emotives = average_emotives(self.modeler.emotives) ## Average the emotives sourced from multiple pathways.
        return

    def get_model(self, name):
        "Retrieve model values by using the model name."
        m = self.modeler.superkb.getModel(name)
        if m is not None:
            m.pop('_id')
            return m
        else:
            return {}

    def get_vector(self, name):
        "Retrieve vector values by using the vector name."
        m = self.modeler.superkb.getVector(name)
        return m

    def clear_stm(self):
        self.__primitive_variables_reset__()
        self.symbols = []
        self.predictions = []
        self.modeler.clear_stm()
        return

    def clear_all_memory(self):
        self.time = 0
        self.last_command = ""
        self.current_emotives = {}
        self.predictions = []
        self.clear_stm()
        self.modeler.superkb.clear_all_memory()
        self.modeler.clear_all_memory()
        self.vector_processor.clear_all_memory() # Re-initialize vector KBs
        return

    def learn(self):
        self.vector_processor.learn()
        model_name = self.modeler.learn() # Returns the name of the model just learned.
        if model_name:
            return f"MODEL|{model_name}"
        # Return empty string for empty/single sequences (no model created)
        return ""

    def delete_model(self, name):
        """Delete model with the given name from both models-kb and RAM."""
        return self.modeler.delete_model(name)

    def update_model(self, name, frequency, emotives):
        """Update the frequency and emotives of model with the given name from models-kb."""
        return self.modeler.update_model(name, frequency, emotives)

    def observe(self, data=None):
        """
        Process incoming observations and trigger sequence learning/predictions.
        
        This is the main entry point for new sensory data. It handles:
        - String symbols (already in symbolic form)
        - Vectors (converted to symbols via vector processor)
        - Emotives (emotional/utility values)
        - Auto-learning when max_sequence_length is reached
        """
        with self.processing_lock:
            self.time += 1
            if data['unique_id'] == '':
                raise Exception(f'Error: no unique_id in observe call from {data["source"]}')
            unique_id = data['unique_id']

            string_data = data["strings"]
            vector_data = data["vectors"]
            emotives_data = data["emotives"]
            if 'path' not in data:
                data['path'] = []
            data['path'] += [f'{self.name}-{self.id}-process']

            self.percept_data = {'strings': string_data, 
                                    'vectors': vector_data, 
                                    'emotives': emotives_data, 
                                    'path': data['path'],
                                    'metadata': data.get('metadata', {})}

            # Initialize symbol containers
            self.symbols = []
            symbols = []  # For string symbols
            v_identified = []  # For vector-derived symbols
            
            # Process vectors through vector processor to get symbolic representations
            if vector_data:
                v_identified = self._process_vectors_(vector_data)
                if v_identified and self.SORT:
                    v_identified.sort()  # Sort for deterministic sequence matching
                    
            # Process strings (already symbolic)
            if string_data:
                s = True
                symbols = string_data[:]  # Copy to avoid modifying original
                if symbols and self.SORT:
                    symbols.sort()  # Sort for deterministic sequence matching
                    
            # Process emotional/utility values
            if emotives_data:
                self._process_emotives_(emotives_data)
            
            # Combine vector-derived and string symbols
            self.symbols = v_identified[:] + symbols[:]
            # Only trigger predictions if we have actual symbolic content
            if vector_data or string_data:
                self.modeler.trigger_predictions = True
            
            # Add current symbols to short-term memory
            self.modeler.setCurrentEvent(self.symbols)
            
            # Generate predictions based on short-term memory state
            if vector_data or string_data:
                self.predictions = self.modeler.processEvents(data['unique_id'])
            
            # Auto-learning: Create a model when short-term memory reaches max length
            # This prevents unbounded memory growth and creates temporal chunks
            auto_learned_model = None
            stm_length = len(self.modeler.STM)
            max_seq_length = self.modeler.max_sequence_length
            
            if max_seq_length > 0 and stm_length >= max_seq_length:
                # Short-term memory is full - time to consolidate into a model
                if stm_length > 1:
                    # Keep the last event as context for the next sequence
                    # This maintains continuity between learned chunks
                    stm_tail = self.modeler.STM[-1]
                    auto_learned_model = self.learn()  # Creates model and clears STM
                    self.modeler.setSTM([stm_tail])  # Start new STM with last event
                    if auto_learned_model:
                        logger.info(f"Auto-learned model: {auto_learned_model}")
                elif stm_length == 1:
                    # Only one event, just learn it
                    auto_learned_model = self.learn()
                    if auto_learned_model:
                        logger.info(f"Auto-learned model: {auto_learned_model}")

            return {'unique_id': unique_id, 'auto_learned_model': auto_learned_model}
            
    def get_predictions(self, unique_id={}):
        """
        Retrieve predictions for a specific observation ID.
        
        If no ID provided, returns the most recent predictions from memory.
        Otherwise queries the database for stored predictions.
        """
        uid = None
        predictions = []

        if unique_id:
            uid = unique_id['unique_id']
            
        if not uid:
            # Return cached predictions from last observe() call
            predictions = self.predictions
        else:
            # Query database for specific prediction record
            prediction_record = self.predictions_kb.find_one({'unique_id': uid}, {'_id': 0})
            if prediction_record is not None:
                predictions = prediction_record['predictions']
        return predictions

    def getGene(self, gene_name):
        """Return the value of a gene parameter"""
        logger.debug(f'getGene called with {gene_name} for {self.name}-{self.id}')
        return getattr(self.modeler, gene_name, None)

    def get_stm(self):
        """Get the current short-term memory"""
        logger.debug(f'get_stm called in {self.name}-{self.id}')
        return list(self.modeler.STM)
    
    def get_percept_data(self):
        """Return percept data"""
        return self.percept_data

    @property
    def cognition_data(self):
        """Return cognition data"""
        return {
            'predictions': self.predictions,
            'emotives': self.current_emotives,
            'symbols': self.symbols,
            'command': self.last_command,
            'metadata': {},
            'path': [],
            'strings': [],
            'vectors': [],
            'short_term_memory': list(self.modeler.STM)
        }

    def update_genes(self, genes):
        """Update gene values"""
        logger.debug(f'update_genes called with {genes} for {self.name}-{self.id}')
        for gene_name, value in genes.items():
            if hasattr(self.modeler, gene_name):
                setattr(self.modeler, gene_name, value)
        return "genes-updated"
