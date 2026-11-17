"""The ranking benchmark (benchmarks/ranking): its data, its reading of responses, its runner and its reports.

Everything here runs in process. The runner is driven through a stand-in
transport that keeps patterns in a dict and ranks with KATO's own
`rank_predictions`; it is not KATO's matching, and it is only there to exercise
the runner's bookkeeping. The same runner against a live service is in
test_ranking_benchmark_live.py.
"""

import gzip
import hashlib
import io
import json
import math
import re
import sys
import tarfile
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.ranking import charts, datasets, report, run, scoring, stats, suite  # noqa: E402
from benchmarks.ranking.client import Kato, KatoError  # noqa: E402
from benchmarks.ranking.generated import Library, Rng, Sampler, zipf_weights  # noqa: E402
from kato.representations.pattern import Pattern  # noqa: E402
from kato.representations.prediction import rank_predictions  # noqa: E402


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------
# generated data

def test_the_generator_gives_the_same_bytes_on_every_machine():
    """Pinned: integer arithmetic only, so no platform, Python or library version can move it."""
    rng = Rng(0)                # the published SplitMix64 outputs for seed 0
    assert [rng.next() for _ in range(3)] == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
    library = Library(seed=20261117, vocabulary=200, patterns=80, occurrences_per_pattern=3, max_events=30)
    assert digest(library.learned_as_units()) == "40c11fa413116dbc"
    assert digest(library.learned_as_windows(10)) == "98709732c8900544"
    assert digest(library.queries(seed=5, count=20)) == "0b002779ae8a600b"
    multi = Library(seed=20261117, vocabulary=200, patterns=80, per_event=(1, 2, 3), max_events=30)
    assert digest(multi.queries(seed=5, count=20, noise=20)) == "bc60f68f441b5ed0"


def test_zipf_weights_are_exact():
    assert zipf_weights(4, 0) == [1, 1, 1, 1]
    assert zipf_weights(4, 2) == [(1 << 40) // rank for rank in (1, 2, 3, 4)]
    for halves in (1, 3, 4):
        weights = zipf_weights(50, halves)
        assert weights == sorted(weights, reverse=True) and weights[0] == 1 << 40
    # exponent 1.5: the ninth weight is 1/27 of the first
    assert zipf_weights(9, 3)[8] == (1 << 40) // 27


def test_the_sampler_follows_its_weights():
    sampler, rng = Sampler([1, 0, 3]), Rng(1)
    drawn = Counter(sampler.draw(rng) for _ in range(4000))
    assert drawn[1] == 0
    assert 0.70 < drawn[2] / 4000 < 0.80


@pytest.mark.parametrize("arguments", [
    {"kind": "mid"}, {"kind": "first"}, {"kind": "span"}, {"kind": "stream"}, {"kind": "end"},
    {"kind": "share", "share": 25, "events_between": (8, 30)},
])
def test_asking_for_more_queries_extends_a_set_without_changing_it(arguments):
    library = Library(seed=3, vocabulary=200, patterns=80, max_events=30)
    assert library.queries(seed=9, count=30, **arguments)[:12] == library.queries(seed=9, count=12, **arguments)


def test_generated_queries_have_the_shape_they_name():
    library = Library(seed=3, vocabulary=200, patterns=80, max_events=30)
    patterns = [[list(event) for event in pattern] for pattern in library.patterns]
    for stm, answer in library.queries(seed=1, count=40, kind="mid", stm_events=5, noise=0):
        assert len(stm) == 5 and answer is not None
        assert any(p[i:i + 5] == stm and p[i + 5] == answer for p in patterns for i in range(len(p) - 5))
    for stm, answer in library.queries(seed=1, count=40, kind="first", stm_events=5, noise=0):
        assert any(p[:5] == stm and p[5] == answer for p in patterns if len(p) > 5)
    for stm, answer in library.queries(seed=1, count=40, kind="end", stm_events=5, noise=0):
        assert answer is None and any(p[-5:] == stm for p in patterns)
    for stm, _ in library.queries(seed=1, count=40, noise=20):
        assert sum(len(event) for event in stm) >= 2


def test_windows_cut_the_stream_of_occurrences():
    library = Library(seed=3, vocabulary=200, patterns=40, max_events=30)
    stream = [event for sequence in library.learned_as_units() for event in sequence]
    windows = library.learned_as_windows(10)
    assert all(len(window) == 10 for window in windows)
    assert [event for window in windows for event in window] == stream[:len(windows) * 10]
    assert len(stream) - len(windows) * 10 < 10


# ----------------------------------------------------------------------------
# public data sets: reading and splitting

def test_a_symbol_is_one_to_one_and_plain():
    assert datasets.symbol("E5") == "E5"
    assert datasets.symbol("a b") == "a%20b"
    assert datasets.symbol("<unk>") == "%3Cunk%3E"
    assert datasets.symbol("%") == "%25"
    assert datasets.symbol("é") == "%C3%A9"
    tokens = ["a,b", "a%2Cb", "a b", "a_b", "'", '"', "\\", "|"]
    symbols = [datasets.symbol(token) for token in tokens]
    assert len(set(symbols)) == len(tokens)
    assert all(re.fullmatch(r"[A-Za-z0-9_.+%-]+", name) for name in symbols)


def test_readers_turn_each_source_into_sequences_of_one_symbol_events():
    hdfs = io.BytesIO(b'BlockId,Label,Type,Features,TimeInterval,Latency\n'
                      b'blk_1,Success,,"[E5,E22,E5]","[0.0, 1.0]",3\nblk_2,Fail,,"[E5]","[0.0]",1\n')
    assert datasets.read_hdfs_traces(hdfs) == [[["E5"], ["E22"], ["E5"]], [["E5"]]]

    msnbc = io.BytesIO(b"% header\nfrontpage news\n% Sequences:\n1 1 2 \n17 \n\n")
    assert datasets.read_msnbc(msnbc) == [[["c01"], ["c01"], ["c02"]], [["c17"]]]

    text = io.BytesIO(b" \n = Title = \n \n The cat sat . It <unk> , then left .\n No full stop\n")
    assert datasets.read_wikitext_sentences(text) == [
        [["The"], ["cat"], ["sat"], ["."]],
        [["It"], ["%3Cunk%3E"], ["%2C"], ["then"], ["left"], ["."]],
        [["No"], ["full"], ["stop"]],
    ]

    xes = io.BytesIO(b'<?xml version="1.0"?><log xmlns="http://www.xes-standard.org/">'
                     b'<global scope="event"><string key="concept:name" value="UNKNOWN"/></global>'
                     b'<trace><string key="concept:name" value="case1"/>'
                     b'<event><string key="concept:name" value="A &amp; B"/><string key="lifecycle:transition" value="START"/></event>'
                     b'<event><string key="lifecycle:transition" value="COMPLETE"/><string key="concept:name" value="C"/></event>'
                     b'</trace><trace><event><string key="concept:name" value="C"/></event></trace></log>')
    assert datasets.read_xes_traces(xes, ("concept:name", "lifecycle:transition")) == [
        [["A%20%26%20B+START"], ["C+COMPLETE"]], [["C+"]]]

    bach = io.BytesIO(b"000106b_,1,YES, NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,F,3, F_M\n"
                      b"000106b_,2,YES, NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,F,3, F_M\n"
                      b"000106b_,3,YES, NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,E,5, C_M\n"
                      b"000206b_,1,YES, NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,NO,E,5, C_M\n")
    assert datasets.read_bach_chords(bach) == [[["F_M"], ["C_M"]], [["C_M"]]]


def test_unix_sessions_are_read_from_the_nested_archive_without_unpacking():
    def gz(text):
        return gzip.compress(text.encode())

    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for name, text in (("UNIX_user_data/USER0.gz", "**SOF**\ncd\n<1>\nls\n**EOF**\n**SOF**\n**EOF**\n"),
                           ("UNIX_user_data/USER1.gz", "**SOF**\nvi\n**EOF**\n"),
                           ("UNIX_user_data/README", "not data")):
            data = gz(text) if name.endswith(".gz") else text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    archive.seek(0)
    assert datasets.read_unix_sessions(archive) == [[["cd"], ["%3C1%3E"], ["ls"]], [], [["vi"]]]


def test_the_split_cuts_what_is_learned_and_keeps_held_out_sequences_whole():
    sequences = [[[f"s{j}"]] * (150 if j == 3 else 1 if j == 5 else 4) for j in range(12)]
    split = datasets.split_by_index(sequences, 4, (0, 1), (3,))
    assert [sequence[0] for sequence in split.learn] == [["s0"], ["s1"], ["s4"], ["s8"], ["s9"]]   # s5 has one event
    assert [len(sequence) for sequence in split.held_out] == [150, 4, 4]
    assert all(len(sequence) <= datasets.MAX_EVENTS for sequence in split.learn)
    with pytest.raises(ValueError):
        datasets.split_by_index(sequences, 4, (0, 1), (1,))


def test_queries_on_held_out_sequences():
    held_out = [[[f"a{i}"] for i in range(2)], [[f"b{i}"] for i in range(9)], [[f"c{i}"] for i in range(130)]]
    queries = suite.next_event_queries(held_out, seed=1, count=500)
    assert len(queries) == 0 + 7 + 98            # every position with two events before it, in the first 100
    assert len({(tuple(map(tuple, stm)), tuple(answer)) for stm, answer in queries}) == len(queries)
    for stm, answer in queries:
        letter, at = answer[0][0], int(answer[0][1:])
        assert 2 <= len(stm) <= 5 and at < 100
        assert stm == [[f"{letter}{i}"] for i in range(max(0, at - 5), at)]
    assert suite.next_event_queries(held_out, 1, 40)[:15] == suite.next_event_queries(held_out, 1, 15)
    assert all(answer != ["b4"] for _, answer in suite.next_event_queries(held_out, 1, 500, skip_answers=frozenset({"b4"})))

    endings = suite.ending_queries(held_out, seed=1, count=10)
    assert sorted(len(stm) for stm, _ in endings) == [2, 5]          # the 130-event sequence is not complete in 100
    assert all(answer is None for _, answer in endings)
    assert [["b8"]] in [stm[-1:] for stm, _ in endings]


def test_a_download_is_checked_against_its_pin(tmp_path):
    (tmp_path / "plain.txt").write_bytes(b"hello")
    good = datasets.Download("https://example.invalid/plain.txt", "plain.txt", 5,
                             sha256=hashlib.sha256(b"hello").hexdigest())
    assert datasets.fetch(good, tmp_path, lambda *a: None) == tmp_path / "plain.txt"
    bad = datasets.Download("https://example.invalid/plain.txt", "plain.txt", 5, sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        datasets.fetch(bad, tmp_path, lambda *a: None)

    with zipfile.ZipFile(tmp_path / "box.zip", "w") as box:
        box.writestr("inner.data", "payload")
    pinned = datasets.Download("https://example.invalid/box.zip", "box.zip", 0,
                               members=(("inner.data", hashlib.sha256(b"payload").hexdigest()),))
    datasets.verify(pinned, tmp_path / "box.zip")
    with pytest.raises(ValueError, match="inner.data"):
        datasets.verify(datasets.Download("https://example.invalid/box.zip", "box.zip", 0,
                                          members=(("inner.data", "0" * 64),)), tmp_path / "box.zip")

    with pytest.raises(ValueError, match="non-HTTPS"):
        datasets.fetch(datasets.Download("http://example.invalid/x", "missing.bin", 1, sha256="0" * 64),
                       tmp_path, lambda *a: None)


def test_every_data_set_names_its_source_and_pins_its_files():
    assert set(datasets.DATASETS) == {"hdfs", "msnbc", "wikitext", "bpi2012", "sepsis", "bach", "unix"}
    for dataset in datasets.DATASETS.values():
        assert dataset.page.startswith("https://") and dataset.licence and dataset.cite and dataset.what
        for download in dataset.downloads:
            assert download.url.startswith("https://")
            assert len(download.sha256) == 64 or all(len(pin) == 64 for _, pin in download.members)
            assert download.sha256 or download.members
    assert [d.key for d in datasets.DATASETS.values() if not d.in_fit] == ["bpi2012", "sepsis", "bach", "unix"]


def test_the_guide_suite_is_what_the_docs_say():
    plans = suite.guide_plans()
    assert [plan.key for plan in plans][:8] == ["gen_base", "hdfs", "msnbc", "wikitext", "bpi2012", "sepsis",
                                                "bach", "unix"]
    assert len(plans) == 14 and sum(len(plan.set_keys) for plan in plans) == 30
    assert len({key for plan in plans for key in plan.set_keys}) == 30
    assert suite.seed_for("guide", "gen_base", "library") == 14633847490704613508


# ----------------------------------------------------------------------------
# reading a response

def prediction(name, future, **values):
    out = dict.fromkeys(scoring.KEYS, 0.0)
    out.update(values)
    out.update({"name": name, "future": future})
    return out


def test_the_client_ranks_as_kato_does():
    """`rank_key` against kato.representations.prediction.rank_predictions, ties and missing values included."""
    predictions = [
        prediction("b" * 40, [["x"]], potential=1.0, frequency=3),
        prediction("a" * 40, [["y"]], potential=1.0, frequency=3),
        prediction("c" * 40, [], potential=2.5, frequency=1),
        prediction("d" * 40, [["x"]], potential=None, frequency=3),
        prediction("e" * 40, [["z"]], potential=-4.0, frequency=7),
    ]
    for key in ("potential", "frequency"):
        ours = sorted(predictions, key=lambda p: scoring.rank_key(p, key), reverse=True)
        theirs = rank_predictions(predictions, key, len(predictions))
        assert [p["name"] for p in ours] == [p["name"] for p in theirs]
        assert max(predictions, key=lambda p: scoring.rank_key(p, key))["name"] == rank_predictions(
            predictions, key, 1)[0]["name"]


def test_the_client_names_a_pattern_as_kato_does():
    for sequence in ([["b"], ["a"]], [["b", "a", "c"], ["x"]], [["s00001"], ["s00001"], ["s00002"]]):
        assert scoring.pattern_name(sequence) == Pattern([sorted(event) for event in sequence]).name


def test_reading_what_each_key_puts_on_top():
    predictions = [
        prediction("a" * 40, [], potential=9.0, similarity=0.2, frequency=1),            # the pattern has ended
        prediction("b" * 40, [["x"], ["q"]], potential=5.0, similarity=0.9, frequency=1),
        prediction("c" * 40, [["y"]], potential=1.0, similarity=0.9, frequency=1),
        prediction("d" * 40, [["y", "w"]], potential=0.5, similarity=0.1, frequency=1),
    ]
    keys = ("potential", "similarity", "frequency")
    read = scoring.read_ranked(predictions, ["y"], keys)
    assert read["top"] == [scoring.NO_EVENT, scoring.RIGHT, scoring.WRONG]      # similarity ties go to 'c', frequency to 'd'
    assert read["future"] == [scoring.WRONG, scoring.RIGHT, scoring.WRONG]
    assert read["rank"] == [3, 1, 2]
    assert read["tied"] == [1, 2, 4]
    # a multi-symbol answer is matched as a set
    assert scoring.read_ranked(predictions, ["w", "y"], keys)["rank"] == [4, 4, 1]
    # a sequence that ended: nothing is right, and a top prediction without a future names no event
    ended = scoring.read_ranked(predictions, None, keys)
    assert ended["top"] == [scoring.NO_EVENT, scoring.WRONG, scoring.WRONG] and ended["rank"] == [0, 0, 0]
    assert scoring.read_ranked([], ["y"], keys) == {"top": [0, 0, 0], "future": [0, 0, 0], "rank": [0, 0, 0],
                                                    "tied": [0, 0, 0]}


def test_reading_a_response_cut_to_a_depth():
    ranked = [prediction("a" * 40, []), prediction("b" * 40, [["x"]]), prediction("c" * 40, [["y"]])]
    assert scoring.read_top_ranked(ranked, ["y"]) == {"top": scoring.NO_EVENT, "future": scoring.WRONG, "rank": 3}
    assert scoring.read_top_ranked(ranked[:1], ["y"]) == {"top": scoring.NO_EVENT, "future": scoring.NO_EVENT, "rank": 0}
    assert scoring.read_top_ranked([], ["y"]) == {"top": scoring.NO_EVENT, "future": scoring.NO_EVENT, "rank": 0}


def test_reading_the_ensemble_figures():
    response = {"future_potentials": [{"next_event": ["x"], "probability": 0.6, "supporting_patterns": 2},
                                      {"next_event": ["z", "y"], "probability": 0.3, "supporting_patterns": 1}],
                "ends_here": 0.1, "chance_posterior": 0.02}
    assert scoring.read_ensemble(response, ["x"]) == {
        "fp_p": 0.6, "fp_right": 1, "p_answer": 0.6, "ends_here": 0.1, "chance": 0.02}
    assert scoring.read_ensemble(response, ["y", "z"])["p_answer"] == 0.3
    assert scoring.read_ensemble(response, ["q"]) == {
        "fp_p": 0.6, "fp_right": 0, "p_answer": 0.0, "ends_here": 0.1, "chance": 0.02}
    assert scoring.read_ensemble(response, None)["fp_right"] == 0
    assert scoring.read_ensemble({"future_potentials": [], "ends_here": None, "chance_posterior": None}, ["x"]) == {
        "fp_p": None, "fp_right": 0, "p_answer": 0.0, "ends_here": None, "chance": None}


def test_the_fingerprint_sees_one_bit_and_ignores_order():
    a, b = prediction("a" * 40, [["x"]], potential=0.1 + 0.2), prediction("b" * 40, [], potential=1.0)
    response = {"predictions": [a, b], "future_potentials": [], "ends_here": 0.5, "chance_posterior": None}
    same = {"predictions": [b, a], "future_potentials": [], "ends_here": 0.5, "chance_posterior": None}
    assert scoring.response_digest(response) == scoring.response_digest(same)
    moved = {**response, "predictions": [{**a, "potential": 0.3}, b]}        # 0.1 + 0.2 is not 0.3
    assert scoring.response_digest(response) != scoring.response_digest(moved)
    assert scoring.response_digest(response) != scoring.response_digest({**response, "ends_here": 0.25})


# ----------------------------------------------------------------------------
# the runner, against a stand-in

class ToyKato:
    """Enough of the REST API to drive the runner. Matching here is a toy; ranking is KATO's function."""

    def __init__(self):
        self.sessions, self.nodes, self.calls = {}, {}, Counter()
        self.corrupt_learns = False
        self.lose_a_pattern = False

    def __call__(self, method, path, payload=None):
        payload = payload or {}
        if path == "/":
            return {"service": "KATO API", "version": "toy"}
        if path == "/health":
            return {"status": "healthy"}
        if path.startswith("/patterns/count"):
            node = self.nodes.get(re.search(r"node_id=([^&]+)", path).group(1), {})
            return {"pattern_count": len(node) - (1 if self.lose_a_pattern and node else 0)}
        if path == "/sessions":
            session = f"s{len(self.sessions)}"
            self.sessions[session] = {"node": payload["node_id"], "stm": [],
                                      "config": {"recall_threshold": 0.1, "max_predictions": 100,
                                                 "rank_sort_algo": "potential", **payload["config"]}}
            return {"session_id": session}
        session, action = re.fullmatch(r"/sessions/([^/]+)/?(.*)", path).groups()
        if session not in self.sessions:
            raise KatoError(404, "no such session", path)
        state = self.sessions[session]
        node = self.nodes.setdefault(state["node"], {})
        self.calls[action or method] += 1
        if method == "DELETE":
            del self.sessions[session]
        elif action == "config":
            state["config"].update(payload["config"])
        elif action == "clear-stm":
            state["stm"] = []
        elif action == "clear-all":
            node.clear()
        elif action == "finalize-training":
            return {"status": "completed", "patterns_processed": len(node), "time_ms": 0.1}
        elif action == "observe-sequence":
            initial = len(state["stm"])
            state["stm"] += [sorted(o["strings"]) for o in payload["observations"]]
            learned = None
            if payload.get("learn_at_end"):
                learned = Pattern(state["stm"]).name
                node.setdefault(learned, [state["stm"], 0])[1] += 1
                state["stm"] = []
                if self.corrupt_learns:
                    learned = "0" * 40
            return {"initial_stm_length": initial, "final_stm_length": len(state["stm"]),
                    "final_learned_pattern": learned}
        elif action == "predictions":
            return self.predict(node, state)
        return {"status": "okay"}

    def predict(self, node, state):
        observed = [name for event in state["stm"] for name in event]
        predictions = []
        for name, (events, frequency) in sorted(node.items()):     # a fixed order, so the sums below are too
            flat = [x for event in events for x in event]
            matched = [i for i, event in enumerate(events) if any(x in observed for x in event)]
            similarity = 2 * sum(1 for x in observed if x in flat) / (len(observed) + len(flat))
            if not matched or similarity < state["config"]["recall_threshold"]:
                continue
            values = {key: (int(name[i:i + 2], 16) % 5) / 4 for i, key in enumerate(scoring.KEYS)}   # ties on purpose
            values.update(potential=similarity + math.log(frequency), similarity=similarity, frequency=frequency)
            predictions.append({"name": name, "future": events[matched[-1] + 1:], **values})
        total = sum(math.exp(p["potential"]) for p in predictions)
        by_event = Counter()
        for p in predictions:
            if p["future"]:
                by_event[tuple(p["future"][0])] += math.exp(p["potential"]) / total
        entries = [{"next_event": list(event), "probability": p, "supporting_patterns": 1}
                   for event, p in sorted(by_event.items(), key=lambda item: (-item[1], item[0]))]
        ranked = rank_predictions(predictions, state["config"]["rank_sort_algo"], state["config"]["max_predictions"])
        return {"predictions": ranked, "future_potentials": entries, "count": len(ranked),
                "ends_here": (1 - sum(by_event.values())) if predictions else None,
                "chance_posterior": 0.0 if predictions else 1.0}


def arguments(tmp_path, *extra):
    return run.parser().parse_args(["--suite", "smoke", "--results-dir", str(tmp_path / "results"),
                                    "--data-dir", str(tmp_path / "data"), "--concurrency", "3", *extra])


def records(tmp_path, name="smoke"):
    return {path.name: [json.loads(line) for line in path.read_text().splitlines()]
            for path in sorted((tmp_path / "results" / name / "sets").glob("*.jsonl"))}


def untimed(record):
    """A stored record without its request times, which differ from run to run."""
    return {**record, "t": {threshold: {k: v for k, v in entry.items() if k != "ms"}
                            for threshold, entry in record["t"].items()}}


@pytest.fixture
def finished(tmp_path):
    toy = ToyKato()
    assert run.run(arguments(tmp_path), log=lambda *a: None, kato=Kato(transport=toy)) == 0
    return tmp_path, toy


def test_a_run_writes_one_record_per_query_and_clears_its_nodes(finished):
    tmp_path, toy = finished
    stored = records(tmp_path)
    assert {name: len(rows) for name, rows in stored.items()} == {
        "gen_small.end.jsonl": 6, "gen_small.mid5.jsonl": 12, "gen_small_multi.mid5.jsonl": 12}
    for rows in stored.values():
        assert [row["i"] for row in rows] == list(range(len(rows)))
        for row in rows:
            assert set(row["t"]) == {"0.1", "0.3", "0.5"}
            for entry in row["t"].values():
                assert all(len(entry[field]) == len(scoring.KEYS) for field in ("top", "future", "rank", "tied"))
                assert "digest" in entry and "capped" not in entry
    assert all(row["answer_symbols"] == 0 for row in stored["gen_small.end.jsonl"])
    record = json.loads((tmp_path / "results" / "smoke" / "run.json").read_text())
    assert record["node_order"] == ["gen_small", "gen_small_multi"]
    assert record["nodes"]["gen_small"]["pattern_count"] == record["nodes"]["gen_small"]["patterns"]
    assert len(record["nodes"]["gen_small"]["latency"]["ms"]) == 12
    assert set(record["nodes"]["gen_small"]["latency"]["by_key_ms"]) == set(scoring.KEYS)
    assert all(not node for node in toy.nodes.values()), "every node is cleared when its queries are done"
    assert not toy.sessions, "every session is deleted"
    assert all(node_id.startswith("rankbench_smoke_") for node_id in toy.nodes)


def test_a_finished_run_asks_nothing_again(finished):
    tmp_path, toy = finished
    before = records(tmp_path)
    again = ToyKato()
    assert run.run(arguments(tmp_path), log=lambda *a: None, kato=Kato(transport=again)) == 0
    assert again.calls["predictions"] == 0 and again.calls["observe-sequence"] == 0
    assert records(tmp_path) == before


def test_more_queries_extend_a_run_and_keep_what_is_stored(finished):
    tmp_path, _ = finished
    before = records(tmp_path)
    more = ToyKato()
    assert run.run(arguments(tmp_path, "--queries", "20"), log=lambda *a: None, kato=Kato(transport=more)) == 0
    after = records(tmp_path)
    assert {name: len(rows) for name, rows in after.items()} == {
        "gen_small.end.jsonl": 10, "gen_small.mid5.jsonl": 20, "gen_small_multi.mid5.jsonl": 20}
    for name, rows in before.items():
        assert after[name][:len(rows)] == rows


def test_an_interrupted_set_is_repaired_and_continued(finished):
    tmp_path, _ = finished
    path = tmp_path / "results" / "smoke" / "sets" / "gen_small.mid5.jsonl"
    whole = path.read_text().splitlines()
    path.write_text("\n".join(whole[:7]) + "\n" + whole[7][:40])          # cut inside the eighth record
    resumed = ToyKato()
    assert run.run(arguments(tmp_path, "--only", "gen_small"), log=lambda *a: None, kato=Kato(transport=resumed)) == 0
    after = path.read_text().splitlines()
    assert after[:7] == whole[:7], "what was stored whole is kept as it was"
    assert [untimed(json.loads(line)) for line in after] == [untimed(json.loads(line)) for line in whole]
    probe = 1 + 12 + 5 * len(scoring.KEYS)                  # the timing pass: a warm-up, 12 requests, 5 per key
    assert resumed.calls["predictions"] == 5 * 3 + probe, "only the five missing queries are asked again"


def test_results_of_another_query_set_are_refused(finished):
    tmp_path, _ = finished
    path = tmp_path / "results" / "smoke" / "sets" / "gen_small.mid5.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[3]["q"] = "0" * 16
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(run.BenchmarkError, match="--fresh"):
        run.stored_records(path, suite.smoke_plans()[0].build(tmp_path, 12).query_sets[0].queries, run.THRESHOLDS)


def test_asking_each_key_separately_gives_what_one_full_response_gives(finished):
    """With a response cap of 4 the runner asks KATO for each key's own top. The stand-in ranks with
    kato.representations.prediction.rank_predictions, so this compares the client's ranking with KATO's."""
    tmp_path, _ = finished
    capped = ToyKato()
    assert run.run(arguments(tmp_path, "--response-cap", "4", "--name", "capped"), log=lambda *a: None,
                   kato=Kato(transport=capped)) == 0
    full, per_key = records(tmp_path), records(tmp_path, "capped")
    went_per_key = 0
    for name, rows in full.items():
        for a, b in zip(rows, per_key[name]):
            for threshold in a["t"]:
                one, other = a["t"][threshold], b["t"][threshold]
                assert [one[field] for field in ("fp_p", "ends_here", "chance")] == [
                    other[field] for field in ("fp_p", "ends_here", "chance")]
                went_per_key += "capped" in other
                assert (one["top"], one["future"], one["rank"]) == (other["top"], other["future"], other["rank"])
    assert went_per_key > 20


def test_a_node_that_did_not_learn_what_was_sent_fails_the_run(tmp_path):
    for fault in ("corrupt_learns", "lose_a_pattern"):
        toy = ToyKato()
        setattr(toy, fault, True)
        lines = []
        assert run.run(arguments(tmp_path, "--name", fault), log=lines.append, kato=Kato(transport=toy)) == 1
        record = json.loads((tmp_path / "results" / fault / "run.json").read_text())
        assert "not usable" in record["nodes"]["gen_small"]["error"]
        assert not records(tmp_path, fault), "no query is asked of a node that failed its check"
        assert all(not node for node in toy.nodes.values()), "the node is cleared all the same"


def test_a_run_refuses_results_measured_another_way(finished):
    tmp_path, _ = finished
    with pytest.raises(run.BenchmarkError, match="other settings"):
        run.run(arguments(tmp_path, "--response-cap", "4"), log=lambda *a: None, kato=Kato(transport=ToyKato()))


def test_clear_nodes_empties_the_suites_nodes_and_nothing_else(tmp_path):
    toy = ToyKato()
    assert run.run(arguments(tmp_path, "--keep-nodes"), log=lambda *a: None, kato=Kato(transport=toy)) == 0
    toy.nodes["someone_elses_node"] = {"x": [[["a"], ["b"]], 1]}
    assert all(toy.nodes[f"rankbench_smoke_{key}"] for key in ("gen_small", "gen_small_multi")), "kept, as asked"
    assert run.run(arguments(tmp_path, "--clear-nodes"), log=lambda *a: None, kato=Kato(transport=toy)) == 0
    assert not toy.nodes["rankbench_smoke_gen_small"] and not toy.nodes["rankbench_smoke_gen_small_multi"]
    assert toy.nodes["someone_elses_node"], "a node of another name is never touched"
    assert not toy.sessions


def test_check_data_reads_every_node_without_kato(tmp_path):
    lines = []
    assert run.run(arguments(tmp_path, "--check-data"), log=lines.append) == 0
    assert len(lines) == 2 and "gen_small:" in lines[0] and "12 mid5" in lines[0]


# ----------------------------------------------------------------------------
# figures

def test_intervals():
    p, low, high = stats.wilson(50, 100)
    assert (p, round(low, 4), round(high, 4)) == (0.5, 0.4038, 0.5962)
    assert stats.wilson(0, 0) == (None, None, None)
    assert stats.wilson(0, 20)[1] == 0.0 and stats.wilson(20, 20)[2] == 1.0

    same = stats.paired([1, 0, 1, 1], [1, 0, 1, 1])
    assert same == {"d": 0.0, "se": 0.0, "n": 4} and stats.level(same)
    ahead = stats.paired([1] * 60 + [0] * 40, [1] * 30 + [0] * 70)
    assert round(ahead["d"], 3) == 0.3 and not stats.level(ahead)
    noise = stats.paired([1, 0] * 50, [0, 1] * 50)
    assert noise["d"] == 0.0 and stats.level(noise)

    mean = stats.mean_of_shares([stats.share([1] * 80 + [0] * 20), stats.share([1] * 20 + [0] * 80)])
    assert round(mean["p"], 3) == 0.5 and round(mean["hi"] - mean["lo"], 3) == round(2 * stats.Z * 0.04 / math.sqrt(2), 3)


def test_area_under_the_roc_curve():
    assert stats.auroc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    assert stats.auroc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == 0.0
    assert stats.auroc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == 0.5
    assert stats.auroc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == 0.75
    assert stats.auroc([0.1, 0.2], [1, 1]) is None


def test_the_guidance_rule(finished):
    tmp_path, _ = finished
    loaded = stats.load_run(tmp_path / "results" / "smoke")
    assert list(loaded["sets"]) == ["gen_small.mid5", "gen_small.end", "gen_small_multi.mid5"]
    cases = stats.cases(loaded)
    assert [case["key"] for case in cases] == ["gen_small.mid5", "gen_small_multi.mid5"]
    result = stats.verdict(loaded, cases[0])
    shares = [share["p"] for share in result["shares"]]
    assert all(shares[k] == max(shares) for k in result["best"])
    assert not set(result["best"]) & set(result["level"])
    best = result["best"][0]
    for k in range(len(loaded["keys"])):
        difference = stats.case_difference(loaded, cases[0], "0.1", "future", best, k)
        low, high = stats.interval(difference)
        assert (k in result["level"]) == (k not in result["best"] and low <= 0 <= high)


def test_two_runs_of_the_same_thing_agree_response_by_response(finished, tmp_path):
    first, _ = finished
    assert run.run(arguments(tmp_path, "--name", "second"), log=lambda *a: None, kato=Kato(transport=ToyKato())) == 0
    a, b = stats.load_run(first / "results" / "smoke"), stats.load_run(tmp_path / "results" / "second")
    assert stats.compare(a, b) == {"same": 90, "different": 0, "only_first": 0, "only_second": 0, "examples": []}
    b["sets"]["gen_small.mid5"]["rows"][2]["t"]["0.3"]["digest"] = "changed"
    assert stats.compare(a, b)["different"] == 1


# ----------------------------------------------------------------------------
# reports

def test_the_reports_are_built_from_the_result_files(finished, tmp_path):
    results, _ = finished
    out = tmp_path / "out"
    report.build(results / "results" / "smoke", out, log=lambda *a: None)
    page = (out / "ranking-benchmark.md").read_text()
    for key in scoring.KEYS:
        assert f"`{key}`" in page
    assert "None" not in page and "nan" not in page.lower()
    for name in re.findall(r"\]\(ranking-benchmark/([a-z]+)\.svg\)", page):
        ElementTree.fromstring((out / "ranking-benchmark" / f"{name}.svg").read_text())      # well-formed
    assert {"headline", "kinds", "situations", "top", "thresholds", "calibration", "endings", "latency"} <= set(
        re.findall(r"\]\(ranking-benchmark/([a-z]+)\.svg\)", page))
    html_page = (out / "ranking-benchmark" / "report.html").read_text()
    assert html_page.startswith("<!DOCTYPE html>") and 'name="threshold"' in html_page and "data-tip=" in html_page
    assert "<script src" not in html_page and "http://" not in html_page.replace("http://www.w3.org/2000/svg", "")
    # the same figures in both: the best key's share in the first case
    loaded = stats.load_run(results / "results" / "smoke")
    best = stats.verdict(loaded, stats.cases(loaded)[0])
    assert f"{best['shares'][best['best'][0]]['p']:.3f}" in page


def test_a_chart_is_a_complete_picture_with_light_and_dark_values():
    svg = charts.ranked_bars("Title", "Subtitle", [
        {"label": "potential", "value": 0.6, "lo": 0.5, "hi": 0.7, "tip": "60% · potential"},
        {"label": "reference", "value": 0.4, "lo": None, "hi": None, "quiet": True, "tip": "40% · reference"}])
    tree = ElementTree.fromstring(svg)
    assert tree.get("role") == "img" and tree.get("aria-label") == "Title. Subtitle"
    assert "prefers-color-scheme: dark" in svg and svg.count("data-tip=") == 2
    assert "<style>" not in charts.ranked_bars("Title", "", [
        {"label": "a", "value": 0.5, "lo": None, "hi": None, "tip": "t"}], standalone=False)
    assert charts.nice_ticks(2613) == [0, 1000, 2000, 3000]
    assert charts.nice_ticks(0.07, 4) == [0, 0.02, 0.04, 0.06, 0.08]
