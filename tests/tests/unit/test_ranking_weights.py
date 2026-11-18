"""benchmarks/ranking/weights.py: future_potentials rebuilt with other candidate weights.

In process; no service needed. The rebuild with e^potential is checked against
KATO's own functions, to the last bit, since the experiment stops on any query
where the two differ.
"""
import itertools
import math

import pytest

from benchmarks.ranking import weights
from kato.informatics.prediction_metrics import bayesian_posteriors, ends_here, future_potentials


def _candidates():
    """Candidates with shared next events, ended patterns, equal potentials and negative ones."""
    futures = [[["b"]], [["b"]], [["c"]], [], [["c", "d"]], [["d", "c"]], [], [["e"]], [["b"]]]
    potentials = [1.25, -0.5, 1.25, 2.0, 0.0, 0.0, -3.75, 0.3, 7.5]
    out = []
    for i, (future, potential) in enumerate(zip(futures, potentials)):
        out.append({
            "name": f"{(i * 7919) % 97:02d}{i}", "future": future, "potential": potential,
            "good_odds": potential * 1.7 - 2.0, "frequency": (i % 4) + 1,
        })
    return out


def _as_kato(entries):
    return [{"next_event": list(e), "probability": p} for p, e in entries]


@pytest.mark.parametrize("order", list(itertools.islice(itertools.permutations(range(9)), 0, 40, 7)))
def test_the_rebuild_with_e_potential_is_katos_own_figures(order):
    candidates = [_candidates()[i] for i in order]
    entries, ended = weights.rebuild(candidates, weights.WEIGHTS[weights.BASE])
    kato = future_potentials(candidates)
    assert [(e["next_event"], e["probability"]) for e in kato] == [(list(e), p) for p, e in entries]
    assert ended == ends_here(candidates)


def test_a_response_agrees_only_when_every_bit_agrees():
    candidates = _candidates()
    entries, ended = weights.rebuild(candidates, weights.WEIGHTS[weights.BASE])
    response = {"predictions": candidates, "future_potentials": _as_kato(entries), "ends_here": ended}
    assert weights.agrees_with_kato(response)
    nudged = [dict(e) for e in response["future_potentials"]]
    nudged[0]["probability"] = math.nextafter(nudged[0]["probability"], 2.0)
    assert not weights.agrees_with_kato({**response, "future_potentials": nudged})
    assert not weights.agrees_with_kato({**response, "ends_here": ended + 1e-15})


def test_uniform_counts_candidates_and_linear_frequency_sums_frequencies():
    candidates = _candidates()
    entries, ended = weights.rebuild(candidates, weights.WEIGHTS["uniform"])
    assert {e: p for p, e in entries}[("b",)] == pytest.approx(3 / 9)
    assert ended == pytest.approx(2 / 9)
    entries, ended = weights.rebuild(candidates, weights.WEIGHTS["frequency, linear"])
    total = sum(c["frequency"] for c in candidates)
    expected = sum(c["frequency"] for c in candidates if c["future"] == [["b"]]) / total
    assert {e: p for p, e in entries}[("b",)] == pytest.approx(expected)


def test_two_to_the_good_odds_shares_out_the_bayesian_posteriors():
    candidates = _candidates()
    posteriors, chance = bayesian_posteriors([c["name"] for c in candidates], [c["good_odds"] for c in candidates])
    entries, ended = weights.rebuild(candidates, weights.WEIGHTS["2^good_odds"])
    expected = sum(posteriors[c["name"]] for c in candidates if c["future"] == [["c"]]) / (1.0 - chance)
    assert {e: p for p, e in entries}[("c",)] == pytest.approx(expected, rel=1e-12)


def test_an_event_is_the_same_whatever_the_order_of_its_symbols():
    result = weights.score(_candidates(), ["d", "c"], weights.WEIGHTS["uniform"])
    assert result["p_answer"] == pytest.approx(1 / 9)          # ['c', 'd'] as stored first
    assert weights.score([], ["b"], weights.WEIGHTS["uniform"])["top_p"] is None


def test_the_top_entry_and_the_probability_given_to_the_answer():
    candidates = _candidates()
    result = weights.score(candidates, ["b"], weights.WEIGHTS[weights.BASE])
    entries, _ = weights.rebuild(candidates, weights.WEIGHTS[weights.BASE])
    assert entries[0][1] == ("b",) and result["right"] and result["top_p"] == entries[0][0]
    assert result["p_answer"] == entries[0][0]
    assert not weights.score(candidates, None, weights.WEIGHTS[weights.BASE])["right"]


def _row(kind, set_key, group, right_base, right_other, p=0.6, ended=0.1):
    w = {name: {"top_p": p, "right": right_base, "p_answer": 0.0, "ends_here": ended} for name in weights.WEIGHTS}
    w["uniform"] = {"top_p": p, "right": right_other, "p_answer": 0.0, "ends_here": ended}
    return {"kind": kind, "set": set_key, "group": group, "w": w}


def test_the_summary_is_the_mean_of_the_kinds_and_pairs_each_weight_with_e_potential():
    rows = ([_row("Generated", "g1", "situation", True, False)] * 3 + [_row("Generated", "g2", "situation", False, False)]
            + [_row("Finance", "f", "data", True, True)] * 2 + [_row("Finance", "f", "data", False, True)] * 2
            + [_row("Finance", "f.end", "ending", False, False, ended=0.9)] * 5)
    summary = {e["weight"]: e for e in weights.summarize(rows)}
    base, other = summary[weights.BASE], summary["uniform"]
    # Generated: sets g1 (1.0) and g2 (0.0) count the same, 0.5; Finance 0.5. Mean of the kinds 0.5.
    assert base["right"] == pytest.approx(0.5) and base["difference"] == 0.0
    # uniform: Generated 0.0, Finance 1.0.
    assert other["right"] == pytest.approx(0.5) and other["by_kind"] == {"Generated": 0.0, "Finance": 1.0}
    assert other["difference"] == pytest.approx(0.0)
    assert base["ends_here_auroc"] == 1.0                     # every ending above every query that went on
    assert base["stated"] == pytest.approx(0.6) and base["calibration_error"] == pytest.approx(abs(0.6 - 5 / 8))
    assert weights.table(weights.summarize(rows)).count("\n") == len(weights.WEIGHTS) + 2


def test_the_table_in_the_docs_is_the_stored_summary():
    import json
    from pathlib import Path
    repo = Path(__file__).resolve().parents[3]
    summary = json.loads((repo / "benchmarks/results/ranking/weights/summary.json").read_text())
    by_name = {e["weight"]: e for e in summary["weights"]}
    doc = (repo / "docs/reference/prediction-object.md").read_text()
    rows = {
        "`e^potential`": weights.BASE, "`2^good_odds` (the shares of `bayesian_posterior`)": "2^good_odds",
        "`e^bayesian_likelihood`": "e^bayesian_likelihood", "`e^predictive_information`": "e^predictive_information",
        "`frequency`": "frequency, linear", "Every candidate equal": "uniform", "`e^frequency`": "e^frequency",
    }
    for label, name in rows.items():
        e = by_name[name]
        diff = "" if name == weights.BASE else (
            f"{e['difference'] * 100:.1f} ({e['low'] * 100:.1f} to {e['high'] * 100:.1f})".replace("-", "−"))
        cells = [label, f"{e['right']:.3f}", diff, f"{e['stated']:.3f}", f"{e['right_when_answered']:.3f}",
                 f"{e['ends_here_auroc']:.3f}"]
        line = "| " + " | ".join(cells).replace("|  |", "| |") + " |"
        assert line in doc, line
