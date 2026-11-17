"""Reading a prediction response: what each ranking key would put on top, and whether it is right.

One response that holds every candidate answers the question for all ranking
keys at once, because KATO ranks by a fixed rule that the client can apply:
highest value first, and among equal values the pattern name that sorts last.
`rank_key` is that rule, taken from `kato.representations.prediction.rank_predictions`.
"""

from __future__ import annotations

import hashlib

# Every value of `rank_sort_algo` except the four affinity-weighted metrics,
# which are deprecated and are None unless a session sets `affinity_emotive`.
KEYS = (
    "potential", "good_odds",
    "similarity", "evidence", "confidence", "snr", "fragmentation", "frequency",
    "bayesian_posterior", "bayesian_prior", "bayesian_likelihood",
    "predictive_information", "confluence",
    "entropy", "normalized_entropy", "global_normalized_entropy",
    "tfidf_score", "itfdf_similarity",
    "event_cohesion", "onset_alignment",
)

# Outcome of a read-out.
NO_EVENT, WRONG, RIGHT = 0, 1, 2


def rank_key(prediction: dict, key: str) -> tuple:
    """KATO's order: sort descending on this. A missing value ranks below every value."""
    value = prediction[key]
    if value is None:
        return (False, 0.0, prediction["name"])
    return (True, value, prediction["name"])


def pattern_name(sequence: list) -> str:
    """The name KATO gives the pattern learned from `sequence`: the SHA-1 of its events as text,
    each event's symbols sorted."""
    events = [sorted(event) for event in sequence]
    return hashlib.sha1(f"{events}".encode(), usedforsecurity=False).hexdigest()


def same_event(a, b) -> bool:
    return sorted(a) == sorted(b)


def _outcome(prediction: dict, answer) -> int:
    if not prediction["future"]:
        return NO_EVENT
    if answer is not None and same_event(prediction["future"][0], answer):
        return RIGHT
    return WRONG


def read_ranked(predictions: list, answer, keys: tuple = KEYS) -> dict:
    """For each ranking key, from predictions that hold every candidate:

    top      outcome of the top prediction: NO_EVENT, WRONG or RIGHT
    future   outcome of the top prediction that has a future (NO_EVENT if none has)
    rank     1-based rank of the first prediction whose next event is right; 0 if none
    tied     how many predictions share the top value (capped at 9999)
    """
    outcomes = [_outcome(prediction, answer) for prediction in predictions]
    result = {"top": [], "future": [], "rank": [], "tied": []}
    for key in keys:
        if not predictions:
            for column in result.values():
                column.append(0)
            continue
        order = [rank_key(prediction, key) for prediction in predictions]
        best = max(order)
        result["top"].append(outcomes[order.index(best)])
        with_future = [k for k, outcome in zip(order, outcomes) if outcome != NO_EVENT]
        result["future"].append(outcomes[order.index(max(with_future))] if with_future else NO_EVENT)
        right = [k for k, outcome in zip(order, outcomes) if outcome == RIGHT]
        if right:
            first_right = max(right)
            result["rank"].append(1 + sum(1 for k in order if k > first_right))
        else:
            result["rank"].append(0)
        result["tied"].append(min(9999, sum(1 for k in order if k[:2] == best[:2])))
    return result


def read_top_ranked(predictions: list, answer) -> dict:
    """The same four readings from a response already ranked by one key and cut to a depth.

    Used when a node holds more candidates than one response can carry. `future`
    and `rank` are then exact only within the depth: NO_EVENT and 0 mean "not
    within the predictions returned".
    """
    outcomes = [_outcome(prediction, answer) for prediction in predictions]
    with_future = [outcome for outcome in outcomes if outcome != NO_EVENT]
    return {
        "top": outcomes[0] if outcomes else NO_EVENT,
        "future": with_future[0] if with_future else NO_EVENT,
        "rank": outcomes.index(RIGHT) + 1 if RIGHT in outcomes else 0,
    }


def read_ensemble(response: dict, answer) -> dict:
    """The three figures computed over all candidates.

    fp_p        probability of the top entry of `future_potentials` (None when it is empty)
    fp_right    whether that entry is the answer
    p_answer    the probability `future_potentials` gives the answer (0.0 when it does not list it)
    ends_here, chance  as returned
    """
    entries = response.get("future_potentials") or []
    p_answer = 0.0
    if answer is not None:
        for entry in entries:
            if same_event(entry["next_event"], answer):
                p_answer = entry["probability"]
                break
    return {
        "fp_p": entries[0]["probability"] if entries else None,
        "fp_right": int(bool(entries) and answer is not None and same_event(entries[0]["next_event"], answer)),
        "p_answer": p_answer,
        "ends_here": response.get("ends_here"),
        "chance": response.get("chance_posterior"),
    }


def _number(value) -> bytes:
    return b"None" if value is None else float(value).hex().encode()


def response_digest(response: dict, keys: tuple = KEYS) -> str:
    """A fingerprint of everything the benchmark reads from a response, to the last bit.

    Two runs whose digests agree got the same candidates with the same values.
    """
    digest = hashlib.sha256()
    for prediction in sorted(response["predictions"], key=lambda p: p["name"]):
        digest.update(prediction["name"].encode())
        for key in keys:
            digest.update(b"|" + _number(prediction[key]))
        digest.update(b"|" + repr([sorted(event) for event in prediction["future"][:1]]).encode() + b"\n")
    for entry in response.get("future_potentials") or []:
        digest.update(repr(sorted(entry["next_event"])).encode() + b"=" + _number(entry["probability"]) + b"\n")
    digest.update(_number(response.get("ends_here")) + b"/" + _number(response.get("chance_posterior")))
    return digest.hexdigest()[:16]
