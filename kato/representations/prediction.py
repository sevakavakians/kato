from collections import Counter
from itertools import chain


def _flatten(symbols):
    """Yield symbols from either a flat list or an event-structured list of lists."""
    for item in symbols:
        if isinstance(item, list):
            yield from item
        else:
            yield item


class Prediction(dict):
    "Pattern prediction."
    def __init__(self, _pattern, matching_intersection, past, present, missing, extras, similarity, number_of_blocks, fuzzy_matches=None, stm_events=None, weighted_similarity=None):
        super().__init__(self)
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
        self['fuzzy_matches'] = fuzzy_matches if fuzzy_matches else []
        self['anomalies'] = []  # Populated below once missing/extras are final
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
        # Note: entropy, normalized_entropy, global_normalized_entropy, and confluence
        # are calculated in pattern_processor.py and set via prediction.update()
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
                raise Exception("Error matching events in predictions! CODE-55 {}".format(e))

        # Calculate event-aligned missing and extras using proper alignment.
        # Symbols are consumed as a multiset so a repeated symbol is only
        # accounted for as many times as it actually matched: an earlier
        # occurrence must not mask a later unobserved one.
        if stm_events and len(stm_events) > 0:
            # Missing: aligned with PRESENT events (pattern events)
            # Each sub-list corresponds to a present event
            # Contains symbols from that pattern event that were not observed (not in matches)
            self['missing'] = []
            unmatched = Counter(self['matches'])
            for present_event in self['present']:
                event_missing = []
                for s in present_event:
                    if unmatched[s] > 0:
                        unmatched[s] -= 1
                    else:
                        event_missing.append(s)
                self['missing'].append(event_missing)

            # Extras: aligned with STM events (observed events)
            # Each sub-list corresponds to an STM event
            # Contains symbols observed in STM but not expected in the pattern present
            self['extras'] = []
            unexpected = Counter(chain(*self['present']))
            for stm_event in stm_events:
                event_extras = []
                for s in stm_event:
                    if unexpected[s] > 0:
                        unexpected[s] -= 1
                    else:
                        event_extras.append(s)
                self['extras'].append(event_extras)
        else:
            # Fallback: Use old flat-list behavior (for backward compatibility)
            self['missing'] = []
            unmatched = Counter(self['matches'])
            for _symbol in chain(*self['present']):
                if unmatched[_symbol] > 0:
                    unmatched[_symbol] -= 1
                else:
                    self['missing'].append(_symbol)
            # extras already set from constructor parameter

        # Anomalies: every symbol that deviates from the pattern, as a flat list.
        # Missing symbols (expected but not observed) come first, then extras
        # (observed but not expected), then the observed token of each fuzzy
        # match (matched, but not spelled the way the pattern has it).
        self['anomalies'] = (
            list(_flatten(self['missing']))
            + list(_flatten(self['extras']))
            + [fm['observed'] for fm in self['fuzzy_matches']]
        )

        __present_length__ = sum([len(_event) for _event in self['present']])
        self['confidence'] = float(len(self['matches'])/__present_length__) if __present_length__ > 0 else 0.0

        # Affinity-weighted metrics (None when disabled)
        self['weighted_similarity'] = weighted_similarity
        self['weighted_evidence'] = None
        self['weighted_confidence'] = None
        self['weighted_snr'] = None

        self.present = self['present']
        # self['past'] = ListValue().add_list().extend(self['past'])
        # self['present'] = ListValue().add_list().extend(self['present'])
        # self['future'] = ListValue().add_list().extend(self['future'])
