from itertools import chain


class Prediction(dict):
    "Pattern prediction."
    def __init__(self, _pattern, matching_intersection, past, present, missing, extras, similarity, number_of_blocks, stm_events=None):
        super(Prediction, self).__init__(self)
        self['type'] = 'prototypical'
        self['name'] = _pattern['name']
        self['frequency'] = _pattern['frequency']
        #self["length"] = _pattern["length"]

        if 'emotives' in _pattern:
            self['emotives'] = _pattern['emotives']
        else:
            self['emotives'] = {}

        self['matches'] = matching_intersection
        self['past'] = past
        self['present'] = present
        self['missing'] = missing
        self['extras'] = extras
        self['potential'] = float(0)
        self['evidence'] = float(len(self['matches'])/_pattern["length"]) if _pattern["length"] > 0 else 0.0
        self['similarity'] = similarity
        self['fragmentation'] = float(number_of_blocks - 1)
        # Calculate SNR with division by zero protection
        # Handle both event-structured and flat extras
        if isinstance(self['extras'], list) and self['extras'] and isinstance(self['extras'][0], list):
            total_extras = sum(len(event) for event in self['extras'])
        else:
            total_extras = len(self['extras']) if isinstance(self['extras'], list) else 0

        denominator = 2.0 * len(self['matches']) + total_extras
        if denominator > 0:
            self['snr'] = float((2.0 * len(self['matches']) - total_extras) / denominator)
        else:
            self['snr'] = float(0)  # Default to 0 when no matches or extras
        self['entropy'] = float(0)
        self['hamiltonian'] = float(0)
        self['grand_hamiltonian'] = float(0)
        self['confluence'] = float(0)
        self['predictive_information'] = float(0)  # Excess entropy / mutual information between past and future
        self['sequence'] = _pattern['pattern_data']
        self['pattern_data'] = _pattern['pattern_data']  # Keep for later popping in pattern_processor

        sequence = _pattern['pattern_data']

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

        # Calculate event-aligned missing and extras using STM event structure
        if stm_events and len(stm_events) > 0:
            # Event-by-event comparison - align with STM events (not pattern events)
            self['missing'] = []
            self['extras'] = []

            for i in range(len(stm_events)):
                stm_event = stm_events[i]
                pattern_event = self['present'][i] if i < len(self['present']) else []

                # Missing: symbols in pattern event but not in corresponding STM event
                event_missing = [s for s in pattern_event if s not in stm_event]
                self['missing'].append(event_missing)

                # Extras: symbols in STM event but not in corresponding pattern event
                event_extras = [s for s in stm_event if s not in pattern_event]
                self['extras'].append(event_extras)
        else:
            # Fallback: Use old flat-list behavior (for backward compatibility)
            self['missing'] = []
            for _symbol in chain(*self['present']):
                if _symbol not in self['matches']:
                    self['missing'].append(_symbol)
            # extras already set from constructor parameter

        __present_length__ = sum([len(_event) for _event in self['present']])
        self['confidence'] = float(len(self['matches'])/__present_length__) if __present_length__ > 0 else 0.0

        self.present = self['present']
        # self['past'] = ListValue().add_list().extend(self['past'])
        # self['present'] = ListValue().add_list().extend(self['present'])
        # self['future'] = ListValue().add_list().extend(self['future'])
