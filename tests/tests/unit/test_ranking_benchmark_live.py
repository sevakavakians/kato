"""The ranking benchmark's runner against a running KATO service.

Skipped when no service answers at KATO_BENCH_URL (default http://localhost:8000).
The smoke suite is run three times on node ids of its own. Once reading one
full response per query, and once with a response cap of 5 so that KATO is
asked for each ranking key's own top: the two must agree, which is the statement
the whole benchmark rests on, that ranking a full response on the client gives
what KATO's `rank_sort_algo` gives. And once more with full responses on nodes
of another name: every response must carry the same fingerprint as in the first
run, that is, every value of every candidate must be the same to the last bit.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.ranking import report, run, scoring, stats, store  # noqa: E402
from benchmarks.ranking.client import Kato  # noqa: E402

URL = os.environ.get("KATO_BENCH_URL", "http://localhost:8000")
NODES = ("gen_small", "gen_small_multi")


@pytest.fixture(scope="module")
def kato():
    service = Kato(URL, timeout=120)
    if not service.healthy():
        pytest.skip(f"no KATO service at {URL}")
    return service


def arguments(folder, prefix, *extra):
    return run.parser().parse_args([
        "--suite", "smoke", "--url", URL, "--results-dir", str(folder), "--data-dir", str(folder / "data"),
        "--node-prefix", prefix, "--concurrency", "2", *extra])


@pytest.fixture(scope="module")
def runs(kato, tmp_path_factory):
    """(folder, node prefix) after a full-response run 'smoke', a per-key run 'per_key' on the same node
    ids, and a second full-response run 'second' on node ids of another name."""
    folder = tmp_path_factory.mktemp("rankbench")
    prefix = f"test_rankbench_{uuid.uuid4().hex[:8]}"       # a test prefix: the suite's own cleanup knows it
    assert run.run(arguments(folder, prefix), log=print) == 0
    assert run.run(arguments(folder, prefix, "--response-cap", "5", "--name", "per_key"), log=print) == 0
    assert run.run(arguments(folder, prefix + "_b", "--name", "second"), log=print) == 0
    return folder, prefix


def stored(folder, name):
    """Every set of a run, by `<set>.jsonl`. A complete set is kept compressed."""
    sets = folder / name / "sets"
    assert all(path.name.endswith(".jsonl.gz") for path in sets.iterdir()), "no working file is left behind"
    keys = sorted(path.name[:-len(".jsonl.gz")] for path in sets.iterdir())
    return {f"{key}.jsonl": [json.loads(line) for line in store.read_lines(sets, key)] for key in keys}


def test_a_live_run_learns_checks_asks_and_records(runs):
    folder, _ = runs
    record = json.loads((folder / "smoke" / "run.json").read_text())
    assert record["kato"]["version"] and record["node_order"] == list(NODES)
    for key in NODES:
        node = record["nodes"][key]
        assert "error" not in node
        assert node["pattern_count"] == node["patterns"] > 0, "KATO holds exactly the patterns the data has"
        assert len(node["latency"]["ms"]) == 12 and all(ms > 0 for ms in node["latency"]["ms"])
    rows = stored(folder, "smoke")
    assert {name: len(found) for name, found in rows.items()} == {
        "gen_small.end.jsonl": 6, "gen_small.mid5.jsonl": 12, "gen_small_multi.mid5.jsonl": 12}
    entries = [row["t"]["0.1"] for found in rows.values() for row in found]
    assert sum(1 for entry in entries if entry["n"] > 0) >= 25, "the queries find candidates"
    assert any(entry["top"][0] == scoring.RIGHT for entry in entries), "and some are answered right"
    for entry in entries:
        if entry["n"] > 0:
            assert entry["ends_here"] is not None and 0.0 <= entry["ends_here"] <= 1.0
            assert entry["fp_p"] is None or 0.0 < entry["fp_p"] <= 1.0 + 1e-12


def test_ranking_a_full_response_on_the_client_gives_what_kato_ranks(runs):
    """Every key, every query, every threshold: top prediction, top prediction with a future, and the
    rank of the first right one, read from KATO's own per-key order, equal the client's reading."""
    folder, _ = runs
    full, per_key = stored(folder, "smoke"), stored(folder, "per_key")
    asked_per_key = 0
    for name, rows in full.items():
        assert len(rows) == len(per_key[name])
        for one, other in zip(rows, per_key[name]):
            assert one["q"] == other["q"]
            for threshold in one["t"]:
                a, b = one["t"][threshold], other["t"][threshold]
                asked_per_key += "capped" in b
                assert (a["top"], a["future"], a["rank"]) == (b["top"], b["future"], b["rank"]), (
                    name, one["i"], threshold)
    assert asked_per_key >= 20, "the cap of 5 must have sent most queries down the per-key path"


def test_two_loads_of_the_same_data_answer_bit_for_bit_the_same(runs):
    """Each run clears its nodes and loads them again, over two sessions whose learns interleave as they
    happen to. The third run does it on nodes of another name."""
    folder, _ = runs
    full, per_key = stored(folder, "smoke"), stored(folder, "per_key")
    for name, rows in full.items():
        for one, other in zip(rows, per_key[name]):
            for threshold in one["t"]:
                a, b = one["t"][threshold], other["t"][threshold]
                for field in ("fp_p", "fp_right", "p_answer", "ends_here", "chance"):
                    assert a[field] == b[field], (name, one["i"], threshold, field)
    # Every response of the first run against the same response of the third: one fingerprint over every
    # candidate's 20 values, its first future event, future_potentials, ends_here and chance_posterior.
    result = stats.compare(stats.load_run(folder / "smoke"), stats.load_run(folder / "second"))
    assert result["different"] == 0, result["examples"]
    assert (result["same"], result["only_first"], result["only_second"]) == (90, 0, 0)


def test_the_benchmarks_nodes_are_empty_afterwards(runs, kato):
    _, prefix = runs
    for key in NODES:
        assert kato.pattern_count(f"{prefix}_smoke_{key}") == 0
        assert kato.pattern_count(f"{prefix}_b_smoke_{key}") == 0


def test_the_reports_build_from_a_live_run(runs, tmp_path):
    folder, _ = runs
    report.build(folder / "smoke", tmp_path, log=lambda *a: None)
    page = (tmp_path / "ranking-benchmark.md").read_text()
    assert "## Request Time" in page and "`potential`" in page
    ElementTree.fromstring((tmp_path / "ranking-benchmark" / "latency.svg").read_text())
    assert (folder / "smoke" / "report.html").read_text().startswith("<!DOCTYPE html>")
