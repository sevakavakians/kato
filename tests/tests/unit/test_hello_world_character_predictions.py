"""
Character-level prediction tests over the learned pattern "hello world".

A single pattern is learned as one character per event:
    [['h'],['e'],['l'],['l'],['o'],[' '],['w'],['o'],['r'],['l'],['d']]

Each test then observes a partial or perturbed sub-sequence and asserts the full
temporal segmentation of the top prediction: past, present, future, missing,
extras, and anomalies.

`missing` is event-aligned with `present` and `extras` with STM, so a clean,
fully-matched observation yields one empty sub-list per event rather than [].
`anomalies` is the flat list of every deviating symbol: missing symbols, then
extras, then the observed token of any fuzzy match.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

PATTERN_TEXT = "hello world"


def _observe_chars(fixture, text):
    """Observe each character of `text` as its own single-symbol event."""
    for char in text:
        fixture.observe({'strings': [char], 'vectors': [], 'emotives': {}})


def _learn_hello_world(fixture):
    """Clear all memory and learn the 'hello world' character pattern."""
    fixture.clear_all_memory()
    fixture.clear_short_term_memory()
    _observe_chars(fixture, PATTERN_TEXT)
    fixture.learn()


def _predict(fixture, text):
    """Clear STM, observe `text` character by character, return predictions."""
    fixture.clear_short_term_memory()
    _observe_chars(fixture, text)
    return fixture.get_predictions()


def test_hello_world_prefix_prediction(kato_fixture):
    """Observing 'hello' should place it entirely in present with ' world' in future."""
    _learn_hello_world(kato_fixture)

    predictions = _predict(kato_fixture, "hello")
    assert len(predictions) > 0, "Should have at least one prediction for 'hello'"
    pred = predictions[0]

    assert pred.get('past', []) == [], \
        f"Past should be empty, got {pred.get('past', [])}"
    assert pred.get('present', []) == [['h'], ['e'], ['l'], ['l'], ['o']], \
        f"Present should be the 'hello' events, got {pred.get('present', [])}"
    assert pred.get('future', []) == [[' '], ['w'], ['o'], ['r'], ['l'], ['d']], \
        f"Future should be the ' world' events, got {pred.get('future', [])}"
    assert pred.get('missing', []) == [[], [], [], [], []], \
        f"Missing should be one empty list per present event, got {pred.get('missing', [])}"
    assert pred.get('extras', []) == [[], [], [], [], []], \
        f"Extras should be one empty list per STM event, got {pred.get('extras', [])}"
    assert pred.get('anomalies', []) == [], \
        f"Anomalies should be empty, got {pred.get('anomalies', [])}"


def test_hello_world_suffix_prediction(kato_fixture):
    """Observing 'world' should place 'hello ' in past and leave future empty."""
    _learn_hello_world(kato_fixture)

    predictions = _predict(kato_fixture, "world")
    assert len(predictions) > 0, "Should have at least one prediction for 'world'"
    pred = predictions[0]

    assert pred.get('past', []) == [['h'], ['e'], ['l'], ['l'], ['o'], [' ']], \
        f"Past should be the 'hello ' events, got {pred.get('past', [])}"
    assert pred.get('present', []) == [['w'], ['o'], ['r'], ['l'], ['d']], \
        f"Present should be the 'world' events, got {pred.get('present', [])}"
    assert pred.get('future', []) == [], \
        f"Future should be empty, got {pred.get('future', [])}"
    assert pred.get('missing', []) == [[], [], [], [], []], \
        f"Missing should be one empty list per present event, got {pred.get('missing', [])}"
    assert pred.get('extras', []) == [[], [], [], [], []], \
        f"Extras should be one empty list per STM event, got {pred.get('extras', [])}"
    assert pred.get('anomalies', []) == [], \
        f"Anomalies should be empty, got {pred.get('anomalies', [])}"


def test_hello_world_perturbed_suffix_prediction(kato_fixture):
    """Observing 'o wxld' should report the dropped and the unexpected symbols.

    The observation drops 'o' and 'r' from the learned tail and introduces an
    unexpected 'x', so present spans 'o world', missing is aligned with present,
    extras is aligned with STM, and every perturbed symbol shows up as an anomaly.
    """
    _learn_hello_world(kato_fixture)

    predictions = _predict(kato_fixture, "o wxld")
    assert len(predictions) > 0, "Should have at least one prediction for 'o wxld'"
    pred = predictions[0]

    assert pred.get('past', []) == [['h'], ['e'], ['l'], ['l']], \
        f"Past should be the 'hell' events, got {pred.get('past', [])}"
    assert pred.get('present', []) == [['o'], [' '], ['w'], ['o'], ['r'], ['l'], ['d']], \
        f"Present should be the 'o world' events, got {pred.get('present', [])}"
    assert pred.get('future', []) == [], \
        f"Future should be empty, got {pred.get('future', [])}"
    assert pred.get('missing', []) == [[], [], [], ['o'], ['r'], [], []], \
        f"Missing should be the dropped 'o' and 'r', got {pred.get('missing', [])}"
    assert pred.get('extras', []) == [[], [], [], ['x'], [], []], \
        f"Extras should be the unexpected 'x', got {pred.get('extras', [])}"
    assert pred.get('anomalies', []) == ['o', 'r', 'x'], \
        f"Anomalies should be ['o', 'r', 'x'], got {pred.get('anomalies', [])}"
