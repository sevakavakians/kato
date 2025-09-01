import copy
from itertools import chain
from collections import Counter
import traceback
from math import log
from kato.informatics.metrics import expectation, classic_expectation, confluence, hamiltonian, grand_hamiltonian

class Prediction(dict):
    "Model prediction."
    def __init__(self, _model, matching_intersection, past, present, missing, extras, similarity, number_of_blocks):
        super(Prediction, self).__init__(self)
        self['type'] = 'prototypical'
        self['name'] = _model['name']
        self['frequency'] = _model['frequency']
        #self["length"] = _model["length"]

        if 'emotives' in _model:
            self['emotives'] = _model['emotives']
        else:
            self['emotives'] = {}

        self['matches'] = matching_intersection
        self['past'] = past
        self['present'] = present
        self['missing'] = missing
        self['extras'] = extras
        self['potential'] = float(0)
        self['evidence'] = float(len(self['matches'])/_model["length"]) if _model["length"] > 0 else 0.0
        self['similarity'] = similarity
        self['fragmentation'] = float(number_of_blocks - 1)
        # Calculate SNR with division by zero protection
        denominator = 2.0 * len(self['matches']) + len(self['extras'])
        if denominator > 0:
            self['snr'] = float((2.0 * len(self['matches']) - len(self['extras'])) / denominator)
        else:
            self['snr'] = float(0)  # Default to 0 when no matches or extras
        self['entropy'] = float(0)
        self['hamiltonian'] = float(0)
        self['grand_hamiltonian'] = float(0)
        self['confluence'] = float(0)
        self['sequence'] = _model['pattern_data']
        self['pattern_data'] = _model['pattern_data']  # Keep for later popping in pattern_processor
        
        sequence = _model['pattern_data']

        __c1 = len(self['past'])
        __c2 = 0
        __event_num = 0
        while __c2 < __c1:
            __c2 += len(sequence[__event_num])
            __event_num += 1

        _e_1 = __event_num
        self['past'] = sequence[:__event_num]

        __c1 += len(self['present'])
        while __c2 < __c1:
            __c2 += len(sequence[__event_num])
            __event_num += 1

        self['present'] = sequence[_e_1:__event_num]
        self['future'] = sequence[__event_num:]

        ## This fixes the problem of some symbols from the tail-end of the last event getting put into the 'past' field instead of 'present'.
        if len(self['past']) > 0:
            try:
                _first_match = self['matches'][0]
                _tail = self['past'][-1].copy()
                _tail.reverse()
                if _first_match in self['past'][-1]:
                    self['present'].insert(0, self['past'][-1])
                    self['past'] = self['past'][:-1]
            except Exception as e:
                raise Exception("Error matching events in predictions! CODE-55 %s" %e)

        self['missing'] = []  ## TODO: Use counts of distinct symbols to include the right amount.
        for _symbol in chain(*self['present']):
            if _symbol not in self['matches']:
                self['missing'].append(_symbol)

        __present_length__ = sum([len(_event) for _event in self['present']])
        self['confidence'] = float(len(self['matches'])/__present_length__) if __present_length__ > 0 else 0.0

        self.present = self['present']
        # self['past'] = ListValue().add_list().extend(self['past'])
        # self['present'] = ListValue().add_list().extend(self['present'])
        # self['future'] = ListValue().add_list().extend(self['future'])
