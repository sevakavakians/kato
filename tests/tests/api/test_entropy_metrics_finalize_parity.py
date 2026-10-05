"""Pattern-intrinsic metrics must not depend on whether finalize-training has run.

`entropy`, `normalized_entropy` (formerly `hamiltonian`),
`global_normalized_entropy` (formerly `grand_hamiltonian`) and `tfidf_score`
describe the pattern, not the match. finalize-training precomputes them over the
whole pattern. Until it runs -- and again after every learn, which invalidates
the stored values for the node -- predictions compute them at request time.

That runtime fallback used `present`, the matched events only, so the same
pattern reported one value before finalization and another after it. These tests
pin that both paths compute over the whole pattern.
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.informatics.metrics import global_normalized_entropy, normalized_entropy  # noqa: E402
from tests.api.test_single_symbol_path_parity import (  # noqa: E402
    _base_url,
    _learn,
    _predict,
    _session,
)

PATTERN = ["fe_a", "fe_a", "fe_b", "fe_c", "fe_d"]
OTHER = ["fe_c", "fe_e", "fe_f"]
# Matches the first three events of PATTERN, so `present` is a strict subset of
# the pattern and the two ways of computing these metrics disagree.
STM = ["fe_a", "fe_b"]
FIELDS = ["entropy", "normalized_entropy", "global_normalized_entropy", "tfidf_score"]


def _prediction_for(session_id, name):
    predictions = _predict(session_id, STM)["predictions"]
    matches = [p for p in predictions if p["name"].removeprefix("PTRN|") == name]
    assert matches, f"pattern {name} was not predicted from {STM}"
    return matches[0]


@pytest.fixture
def trained():
    session_id, _ = _session()
    name = _learn(session_id, PATTERN)
    _learn(session_id, OTHER)
    return session_id, name


def test_fallback_computes_over_the_whole_pattern(trained):
    """Before finalize-training, the value is the whole pattern's, not `present`'s."""
    session_id, name = trained
    prediction = _prediction_for(session_id, name)

    total_symbols = len(set(PATTERN) | set(OTHER))
    present = [s for event in prediction["present"] for s in event]
    assert sorted(present) != sorted(PATTERN), "test needs present to differ from the pattern"

    assert prediction["normalized_entropy"] == pytest.approx(
        normalized_entropy(PATTERN, total_symbols), rel=1e-12)
    assert prediction["normalized_entropy"] != pytest.approx(
        normalized_entropy(present, total_symbols), rel=1e-12)

    # P(symbol) = share of the node's patterns containing it. fe_d is in the
    # pattern's future, outside `present`, and must still get its probability.
    patterns = [set(PATTERN), set(OTHER)]
    probabilities = {s: sum(s in p for p in patterns) / len(patterns) for s in set(PATTERN)}
    assert prediction["global_normalized_entropy"] == pytest.approx(
        global_normalized_entropy(PATTERN, probabilities, total_symbols), rel=1e-12)


def test_values_match_before_and_after_finalize(trained):
    """The same pattern reports the same metrics whichever path computed them."""
    session_id, name = trained
    before = _prediction_for(session_id, name)

    resp = requests.post(f"{_base_url()}/sessions/{session_id}/finalize-training", timeout=60)
    resp.raise_for_status()
    assert resp.json()["patterns_processed"] >= 2

    after = _prediction_for(session_id, name)
    for field in FIELDS:
        assert after[field] == pytest.approx(before[field], rel=1e-12, abs=1e-15), field
