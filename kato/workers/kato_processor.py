# cimport cython
import logging
from os import environ
import traceback
from typing import Counter
from multiprocessing import cpu_count, Lock

from kato.workers.classifier import Classifier
from kato.workers.modeler import Modeler
from kato.informatics.metrics import average_emotives

import grpc
from kato import kato_proc_pb2_grpc
from google.protobuf.struct_pb2 import Struct, ListValue
from google.protobuf.json_format import ParseDict, MessageToDict
from kato.kato_proc_pb2 import google_dot_protobuf_dot_empty__pb2 as pb_empty
from kato.kato_proc_pb2 import Prediction, Observation

EMPTY = pb_empty.Empty()


logger = logging.getLogger('kato.workers.kato-processor')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


class KatoProcessor:
    def __init__(self, genome_manifest, **kwargs):
        '''genome is the specific kato processor's genes.'''
        self.genome_manifest = genome_manifest
        self.id = self.genome_manifest['id']
        self.name = self.genome_manifest["name"]
        self.vector_classifier = self.genome_manifest["classifier"]
        self.agent_name = environ['HOSTNAME']
        logger.info(" Starting KatoProcessor ID: %s" %self.id)

        self.SORT = self.genome_manifest["sort"]
        self.time = 0

        self.procs_for_searches = int(cpu_count())

        self.genome_manifest["kb_id"] = self.id
        self.classifier = Classifier(self.procs_for_searches, **self.genome_manifest)
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
        logger.debug(f'__primitive_variables_reset__ called in {self.name}-{self.id}')
        self.symbols = []
        self.current_emotives = {}
        self.last_command = ""
        self.modeler.v_identified = []
        self.percept_data = {}
        self.percept_data_vector = None
        return

    def _process_vectors_(self, vector_data):
        symbols = self.classifier.process(vector_data)
        return symbols

    def _process_emotives_(self, emotives):
        logger.debug(emotives)
        self.modeler.emotives += [emotives]
        self.current_emotives = average_emotives(self.modeler.emotives) ## Average the emotives sourced from multiple pathways.
        logger.debug(self.current_emotives)
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

    def clear_wm(self):
        logger.debug(f'clear_wm called in {self.name}-{self.id}')
        self.__primitive_variables_reset__()
        self.symbols = []
        self.predictions = []
        self.modeler.clear_wm()
        return

    def clear_all_memory(self):
        logger.debug(f'clear_all_memory called in {self.name}-{self.id}')
        self.time = 0
        self.last_command = ""
        self.current_emotives = {}
        self.predictions = []
        self.clear_wm()
        self.modeler.superkb.clear_all_memory()
        self.modeler.clear_all_memory()
        self.classifier.clear_all_memory() # Re-initialize vector KBs
        return

    def learn(self):
        logger.debug(f'learn called in {self.name}-{self.id}')
        self.classifier.learn()
        model_name = self.modeler.learn() # Returns the name of the model just learned.
        if not model_name:
            return
        return f"MODEL|{model_name}"

    def delete_model(self, name):
        """Delete model with the given name from both models-kb and RAM."""
        return self.modeler.delete_model(name)

    def update_model(self, name, frequency, emotives):
        """Update the frequency and emotives of model with the given name from models-kb."""
        return self.modeler.update_model(name, frequency, emotives)

    def observe(self, data=None):
        "Get observations (percepts (strings, vectors), utilities, actions, commands)"
        with self.processing_lock:
            logger.debug(f'{data}')
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

            self.symbols = []
            symbols = []
            v_identified = []
            if vector_data:
                v_identified = self._process_vectors_(vector_data)
                if v_identified and self.SORT:
                    v_identified.sort()
            if string_data:
                s = True
                symbols = string_data[:]  ## Strings are symbols, already.
                if symbols and self.SORT:
                    symbols.sort()
            if emotives_data:
                self._process_emotives_(emotives_data)
            
            self.symbols = v_identified[:] + symbols[:]
            if vector_data or string_data:
                self.modeler.trigger_predictions = True
            
            self.modeler.setCurrentEvent(self.symbols)
            if vector_data or string_data:
                self.predictions = self.modeler.processEvents(data['unique_id'])

            ### Add WM length check and reduce size:
            if self.modeler.max_sequence_length != 0 and (sum(len(x) for x in self.modeler.WM) >= self.modeler.max_sequence_length):
    #                if self.modeler.max_sequence_length != 0 and (len(self.modeler.WM) >= self.modeler.max_sequence_length):
                if len(self.modeler.WM) > 1:
                    wm_tail = self.modeler.WM[-1]  ## Keep the last event to set as first event in new sequence.
                    self.learn()  ##  Without using the network-wide 'learn' command, this will just learn what's in this CP's WM and, clear out the WM.
                    self.modeler.setWM([wm_tail])
                else:
                    self.learn()  ##  Without using the network-wide 'learn' command, this will just learn what's in this CP's WM and, clear out the WM.

            return unique_id
            
    def get_predictions(self, unique_id={}):
        logger.debug(f'get_prediction with unique_id {unique_id} {self.name}-{self.id}')
        uid = None
        predictions = []

        if unique_id:
            uid = unique_id['unique_id']
        if not uid:
            predictions = self.predictions
        else:
            prediction_record = self.predictions_kb.find_one({'unique_id': uid}, {'_id': 0})
            if prediction_record is not None:
                predictions = prediction_record['predictions']
        return predictions

    def getGene(self, gene_name):
        """Return the value of a gene parameter"""
        logger.debug(f'getGene called with {gene_name} for {self.name}-{self.id}')
        return getattr(self.modeler, gene_name, None)

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
            'working_memory': list(self.modeler.WM)
        }

    def update_genes(self, genes):
        """Update gene values"""
        logger.debug(f'update_genes called with {genes} for {self.name}-{self.id}')
        for gene_name, value in genes.items():
            if hasattr(self.modeler, gene_name):
                setattr(self.modeler, gene_name, value)
        return "genes-updated"
