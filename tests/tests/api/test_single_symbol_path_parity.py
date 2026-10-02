"""The single-symbol fast path must be indistinguishable from the normal path.

A state of one symbol is dispatched to a cheaper candidate-selection strategy: it
reads patterns whose `first_token` matches straight out of ClickHouse instead of
running the filter pipeline. That is a legitimate optimisation of *selection*.
What it must not change is the prediction.

It did. The fast path used to compute its own metrics and return early, so a
one-symbol STM produced predictions missing fourteen fields the normal path
returns, and disagreeing on three it did return:

  * `potential` -- the ranking key -- omitted the `itfdf_similarity` term, so
    scores from the two paths were not comparable at all;
  * `snr` used m/(m+x) where Prediction uses (2m-x)/(2m+x);
  * `evidence` divided by a different length.

Client code reading `prediction['predictive_information']` therefore worked on a
two-symbol STM and raised KeyError on a one-symbol one.

These tests pin the contract rather than the implementation: whatever the two
strategies do internally, a caller must not be able to tell which one ran.
"""

import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _base_url():
    return os.environ.get("KATO_BASE_URL", "http://localhost:8000")


def _session(node_id=None):
    if node_id is None:
        node_id = f"test_sspath_{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{_base_url()}/sessions", json={
        "node_id": node_id, "config": {}, "metadata": {}, "ttl_seconds": 180,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["session_id"], node_id


def _learn(session_id, tokens, emotives=None):
    base = _base_url()
    for token in tokens:
        payload = {"strings": [token]}
        if emotives:
            payload["emotives"] = emotives
        requests.post(f"{base}/sessions/{session_id}/observe", json=payload, timeout=20).raise_for_status()
    name = requests.post(f"{base}/sessions/{session_id}/learn", json={}, timeout=20).json()["pattern_name"]
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    return name.removeprefix("PTRN|")


def _predict(session_id, observe):
    """Observe `observe` tokens one event at a time, then read predictions."""
    base = _base_url()
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    for token in observe:
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json={"strings": [token]}, timeout=20).raise_for_status()
    return requests.get(f"{base}/sessions/{session_id}/predictions", timeout=20).json()


# ------------------------------------------------------------------ shape


def test_one_symbol_returns_the_same_fields_as_two():
    """The field set must not depend on how many symbols are in STM.

    This is the regression that started it: fourteen fields were absent on the
    one-symbol path, so the same client code raised KeyError for one STM length
    and worked for another.
    """
    session_id, _ = _session()
    _learn(session_id, ["sp_a", "sp_b", "sp_c", "sp_d"], emotives={"joy": 0.5})

    one = _predict(session_id, ["sp_a"])["predictions"]
    two = _predict(session_id, ["sp_a", "sp_b"])["predictions"]
    assert one and two, "both STM lengths should predict this pattern"

    missing_from_fast = set(two[0]) - set(one[0])
    extra_on_fast = set(one[0]) - set(two[0])
    assert not missing_from_fast, f"one-symbol path is missing: {sorted(missing_from_fast)}"
    assert not extra_on_fast, f"one-symbol path has fields the normal path lacks: {sorted(extra_on_fast)}"


@pytest.mark.parametrize("field", [
    "predictive_information", "confluence", "entropy", "normalized_entropy",
    "global_normalized_entropy", "itfdf_similarity", "tfidf_score",
    "pattern_probability", "bayesian_prior", "bayesian_likelihood",
    "bayesian_posterior", "weighted_strength", "type", "sequence",
])
def test_one_symbol_populates_every_previously_missing_field(field):
    """Each of the fourteen, named individually so a regression says which one."""
    session_id, _ = _session()
    _learn(session_id, ["sq_a", "sq_b", "sq_c"], emotives={"joy": 0.4})

    predictions = _predict(session_id, ["sq_a"])["predictions"]
    assert predictions, "should predict from a single symbol"
    assert field in predictions[0], f"{field} absent on the single-symbol path"
    assert predictions[0][field] is not None


# ------------------------------------------------------------------ values


def test_one_symbol_potential_uses_the_shared_formula():
    """`potential` is the ranking key, so the two paths must compute it alike.

    The fast path used the pre-potential formula -- the real one minus
    `itfdf_similarity` -- which made its scores incomparable with the normal
    path's rather than merely imprecise.
    """
    session_id, _ = _session()
    _learn(session_id, ["sr_a", "sr_b", "sr_c", "sr_d"], emotives={"joy": 0.5})

    prediction = _predict(session_id, ["sr_a"])["predictions"][0]
    frag = prediction["fragmentation"]
    expected = (
        (prediction["evidence"] + prediction["confidence"]) * prediction["snr"]
        + prediction["itfdf_similarity"]
        + (0.0 if frag == -1 else 1.0 / (frag + 1))
    )
    assert prediction["potential"] == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_one_symbol_snr_uses_the_prediction_formula():
    """snr is (2m - x) / (2m + x), not m / (m + x).

    The two agree only when there are no extras, which is exactly the case a
    single-symbol smoke test hits -- so the divergence survived unnoticed.
    """
    session_id, _ = _session()
    _learn(session_id, ["ss_a", "ss_b", "ss_c"])
    # An extra symbol in the observed event gives x > 0, where the formulas differ.
    base = _base_url()
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    requests.post(f"{base}/sessions/{session_id}/observe",
                  json={"strings": ["ss_a", "ss_unexpected"]}, timeout=20)
    predictions = requests.get(f"{base}/sessions/{session_id}/predictions", timeout=20).json()["predictions"]
    assert predictions, "a single event with one matching symbol should still predict"

    prediction = predictions[0]
    matches = len(prediction["matches"])
    extras = prediction["extras"]
    x = sum(len(e) for e in extras) if extras and isinstance(extras[0], list) else len(extras)
    denominator = 2.0 * matches + x
    expected = (2.0 * matches - x) / denominator if denominator > 0 else 0.0
    assert prediction["snr"] == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_one_symbol_reports_future_potentials():
    """The ensemble pass now runs for one symbol too.

    It did not before -- the fast path returned ahead of it and the endpoint
    answered with an empty list, which was documented as "the honest answer"
    because the figure genuinely had not been computed.
    """
    session_id, _ = _session()
    _learn(session_id, ["st_a", "st_b", "st_c"])

    response = _predict(session_id, ["st_a"])
    assert response["predictions"], "should predict from a single symbol"
    potentials = response["future_potentials"]
    assert potentials, "future_potentials should be populated for a single-symbol state"
    entry = potentials[0]
    for key in ("future", "aggregate_potential", "supporting_patterns", "total_weighted_frequency"):
        assert key in entry, f"future_potentials entry missing {key}"


# ------------------------------------------------------------------ regressions


def test_one_symbol_still_filters_retired_patterns():
    """Retirement filtering lives in the searcher, which the fast path skips.

    Moving the metrics into the shared tail removed the fast path's own call to
    the barrier; it is now applied once, after selection, for both strategies.
    Without it a retired pattern reappears for one-symbol states only.
    """
    session_id, _ = _session()
    name = _learn(session_id, ["su_a", "su_b"])
    assert _predict(session_id, ["su_a"])["predictions"], "should predict before retiring"

    requests.post(f"{_base_url()}/sessions/{session_id}/patterns/retire",
                  json={"pattern_ids": [name]}, timeout=20).raise_for_status()

    assert _predict(session_id, ["su_a"])["predictions"] == [], \
        "retired pattern resurfaced on the single-symbol path"


def test_one_symbol_predictions_are_event_structured():
    """Segmentation must stay event-structured, not flat symbol lists."""
    session_id, _ = _session()
    _learn(session_id, ["sv_a", "sv_b", "sv_c"])

    prediction = _predict(session_id, ["sv_a"])["predictions"][0]
    for field in ("present", "future", "missing"):
        value = prediction[field]
        assert isinstance(value, list)
        for event in value:
            assert isinstance(event, list), f"{field} should be event-structured, got {value!r}"


def test_one_symbol_is_deterministic():
    """Same input, same output -- including the newly shared metrics."""
    session_id, _ = _session()
    for i in range(3):
        _learn(session_id, ["sw_shared", f"sw_tail{i}"])

    first = _predict(session_id, ["sw_shared"])["predictions"]
    for _ in range(3):
        again = _predict(session_id, ["sw_shared"])["predictions"]
        assert [p["name"] for p in again] == [p["name"] for p in first]
        assert [p["potential"] for p in again] == [p["potential"] for p in first]
