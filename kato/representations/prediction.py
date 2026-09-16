import heapq
from collections import Counter
from itertools import chain


def rank_predictions(predictions, metric, limit):
    """Return the `limit` highest-ranked predictions, best first.

    Ranks on ``(predictions[metric], predictions['name'])`` rather than the
    metric alone. The tie-breaker is load-bearing, not cosmetic: the order
    predictions arrive in is NOT stable across requests. Candidates come out of
    a ``set`` -- and string hashing is randomised per process, so each uvicorn
    worker iterates them in a different order -- and batch results are gathered
    with ``concurrent.futures.as_completed``. Because ``heapq.nlargest`` keeps
    the first of equal keys and ``sorted`` is stable, ranking on the metric
    alone let arrival order decide which of several equally-ranked predictions
    came first, and once `limit` truncated the list, which ones were returned at
    all. That breaks KATO's central guarantee that the same inputs produce the
    same outputs.

    Pattern names are unique, so ``(metric, name)`` is a total order and the
    result cannot depend on the order `predictions` is supplied in.

    Args:
        predictions: Iterable of prediction dicts; each needs `metric` and 'name'.
        metric: Name of the ranking field (KATO's ``rank_sort_algo``).
        limit: Maximum number of predictions to return.

    Returns:
        List of at most `limit` predictions, highest-ranked first.

    Raises:
        KeyError: If a prediction lacks `metric` or 'name'.
    """
    def key(prediction):
        return (prediction[metric], prediction['name'])

    return sorted(heapq.nlargest(limit, predictions, key=key), key=key, reverse=True)


def _flatten(symbols):
    """Yield symbols from either a flat list or an event-structured list of lists."""
    for item in symbols:
        if isinstance(item, list):
            yield from item
        else:
            yield item


def _event_of(offsets, flat_index):
    """Index of the event containing flat position `flat_index` (offsets = cumulative starts)."""
    for event_index in range(len(offsets) - 1, -1, -1):
        if flat_index >= offsets[event_index]:
            return event_index
    return 0


def _offsets(events):
    out, total = [], 0
    for event in events:
        out.append(total)
        total += len(event)
    return out


def _flat_event_index(events):
    """Event index for every flat position."""
    return [i for i, event in enumerate(events) for _ in event]


def refine_alignment_by_events(pattern_events, stm_events, pattern_positions, state_positions, max_passes=None):
    """
    Re-attribute matched positions of repeated symbols using event structure.

    The matcher aligns the *flattened* pattern and STM, so when a symbol recurs
    it cannot tell which occurrence an observation refers to; difflib's
    longest-run tie-break then decides, blind to event boundaries. This pass
    moves individual matches between occurrences of the same symbol without
    changing how many symbols matched, which symbols matched, or the order of
    the alignment - so `matches`, `similarity`, `evidence` and `snr` are
    untouched; only which event carries a `missing`/`extras` entry (and, for a
    lone symbol, where `present` starts) can change.

    Rules, applied until none fires:
    - Event-mate (pattern side): a matched symbol prefers the pattern event
      where the other symbols of its observed event matched. If some other
      pattern event has strictly more of those mates and holds an unmatched
      occurrence of the same symbol, move there.
    - Event-mate (observed side): the mirror, re-attributing an extra when an
      observed symbol recurs.
    - Tightness: a symbol with no event evidence (it is alone in its observed
      event) prefers the occurrence that leaves the fewest symbols missing,
      i.e. the tightest `present` span - a lone observed ['x'] matches an exact
      pattern event ['x'] rather than the 'x' of ['x','y'].
    Every move must keep both position sequences strictly increasing against
    the neighbouring pairs.

    Termination: each event-mate move strictly raises the number of pair-pairs
    that share both a pattern event and an observed event; a tightness move
    (allowed only for pairs with no observed-event mates) leaves that number
    unchanged and strictly lowers the missing count. The lexicographic
    potential is bounded, so the loop ends; a pass cap is kept as a backstop.

    Known limits: difflib's blocks are not always a maximum common subsequence,
    and this pass never adds matches; two equal-cost alignments with no event
    evidence and equal tightness keep difflib's choice.
    """
    pairs = list(zip(pattern_positions, state_positions))
    if not pairs:
        return list(pattern_positions), list(state_positions)

    pattern_events = [list(e) for e in pattern_events]
    stm_events = [list(e) for e in stm_events]
    p_flat = [sym for e in pattern_events for sym in e]
    s_flat = [sym for e in stm_events for sym in e]
    p_event = _flat_event_index(pattern_events)
    s_event = _flat_event_index(stm_events)
    p_offsets = _offsets(pattern_events)
    s_offsets = _offsets(stm_events)
    matched_p = {q for q, _ in pairs}
    matched_s = {j for _, j in pairs}

    # Nothing to re-attribute unless an unmatched occurrence of a matched symbol exists.
    matched_syms_p = {p_flat[q] for q in matched_p}
    matched_syms_s = {s_flat[j] for j in matched_s}
    ambiguous_p = any(p_flat[i] in matched_syms_p for i in range(len(p_flat)) if i not in matched_p)
    ambiguous_s = any(s_flat[i] in matched_syms_s for i in range(len(s_flat)) if i not in matched_s)
    if not ambiguous_p and not ambiguous_s:
        return list(pattern_positions), list(state_positions)

    def missing_count(matched):
        first, last = p_event[min(matched)], p_event[max(matched)]
        return sum(len(pattern_events[e]) for e in range(first, last + 1)) - len(pairs)

    def unmatched_in_event(events_flat_index, offsets, events, matched, event_index, symbol, lo, hi):
        start = offsets[event_index]
        for pos in range(start, start + len(events[event_index])):
            if pos not in matched and events_flat_index[pos] == symbol and lo < pos < hi:
                return pos
        return None

    cap = max_passes if max_passes is not None else len(pairs) * len(pairs) + 2
    for _ in range(cap):
        moved = False
        for k, (q, j) in enumerate(pairs):
            symbol = p_flat[q]
            prev_q, prev_j = pairs[k - 1] if k > 0 else (-1, -1)
            next_q, next_j = pairs[k + 1] if k + 1 < len(pairs) else (len(p_flat), len(s_flat))

            # Event-mate rule, pattern side.
            observed_event = s_event[j]
            mates = Counter(p_event[q2] for k2, (q2, j2) in enumerate(pairs) if k2 != k and s_event[j2] == observed_event)
            if mates:
                best = max(mates.values())
                winners = [e for e, n in mates.items() if n == best]
                if len(winners) == 1 and best > mates[p_event[q]]:
                    p = unmatched_in_event(p_flat, p_offsets, pattern_events, matched_p, winners[0], symbol, prev_q, next_q)
                    if p is not None:
                        matched_p.discard(q)
                        matched_p.add(p)
                        pairs[k] = (p, j)
                        moved = True
                        break
            else:
                # Tightness rule: no event evidence, prefer the occurrence with the tightest present.
                current = missing_count(matched_p)
                best_pos, best_missing = None, current
                for e in range(len(pattern_events)):
                    if e == p_event[q]:
                        continue
                    p = unmatched_in_event(p_flat, p_offsets, pattern_events, matched_p, e, symbol, prev_q, next_q)
                    if p is None:
                        continue
                    candidate = (matched_p - {q}) | {p}
                    m = missing_count(candidate)
                    if m < best_missing:
                        best_pos, best_missing = p, m
                if best_pos is not None:
                    matched_p.discard(q)
                    matched_p.add(best_pos)
                    pairs[k] = (best_pos, j)
                    moved = True
                    break

            # Event-mate rule, observed side (re-attributes an extra).
            pattern_event = p_event[q]
            smates = Counter(s_event[j2] for k2, (q2, j2) in enumerate(pairs) if k2 != k and p_event[q2] == pattern_event)
            if smates:
                best = max(smates.values())
                winners = [f for f, n in smates.items() if n == best]
                if len(winners) == 1 and best > smates[s_event[j]]:
                    j_new = unmatched_in_event(s_flat, s_offsets, stm_events, matched_s, winners[0], symbol, prev_j, next_j)
                    if j_new is not None:
                        matched_s.discard(j)
                        matched_s.add(j_new)
                        pairs[k] = (q, j_new)
                        moved = True
                        break
        if not moved:
            break

    return [q for q, _ in pairs], [j for _, j in pairs]



def segment_by_alignment(pattern_events, stm_events, pattern_positions, state_positions):
    """
    Temporal segmentation from matched positions rather than symbol identity.

    pattern_positions / state_positions are the flat indices (into the
    flattened pattern and the flattened STM) that the matcher paired up.
    Positions are first refined event-wise (refine_alignment_by_events) so a
    repeated symbol is attributed to the event its observed neighbours point at.
    Then `present` starts at the event of the first matched position, `missing`
    lists the unmatched positions of each present event, and `extras` lists the
    unmatched positions of each STM event.

    Returns (past, present, future, missing, extras), all event-structured.
    """
    pattern_events = [list(e) for e in pattern_events]
    stm_events = [list(e) for e in stm_events]
    pattern_positions, state_positions = refine_alignment_by_events(
        pattern_events, stm_events, pattern_positions, state_positions)
    matched_pattern = set(pattern_positions)
    matched_state = set(state_positions)
    p_offsets = _offsets(pattern_events)

    if matched_pattern:
        first_event = _event_of(p_offsets, min(matched_pattern))
        last_event = _event_of(p_offsets, max(matched_pattern))
    else:  # nothing matched (only reachable with recall_threshold 0): everything is "present"
        first_event, last_event = 0, len(pattern_events) - 1

    past = pattern_events[:first_event]
    present = pattern_events[first_event:last_event + 1]
    future = pattern_events[last_event + 1:]

    missing = []
    for event_index in range(first_event, last_event + 1):
        start = p_offsets[event_index]
        event = pattern_events[event_index]
        missing.append([sym for k, sym in enumerate(event) if start + k not in matched_pattern])

    extras = []
    s_offsets = _offsets(stm_events)
    for event_index, event in enumerate(stm_events):
        start = s_offsets[event_index]
        extras.append([sym for k, sym in enumerate(event) if start + k not in matched_state])

    return past, present, future, missing, extras


class Prediction(dict):
    "Pattern prediction."
    def __init__(self, _pattern, matching_intersection, past, present, missing, extras, similarity, number_of_blocks, fuzzy_matches=None, stm_events=None, weighted_similarity=None, alignment=None):
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

        if alignment is not None and stm_events:
            # Segment from the matcher's positions (exact-match path). This is
            # unambiguous for repeated symbols and for matches that begin or end
            # mid-event, and needs no symbol-identity heuristics.
            pattern_positions, state_positions = alignment
            (self['past'], self['present'], self['future'],
             self['missing'], self['extras']) = segment_by_alignment(
                sequence, stm_events, pattern_positions, state_positions)
        else:
            # Legacy segmentation by symbol counts (fuzzy-match path, or callers
            # that provide no alignment): derive event boundaries from the flat
            # past/present lengths, then account for symbols as a multiset.
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
                    raise Exception(f"Error matching events in predictions! CODE-55 {e}")

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
