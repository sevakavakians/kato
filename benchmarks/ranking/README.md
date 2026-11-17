# Ranking Benchmark

Which `rank_sort_algo` should a session use? This benchmark measures it on a running KATO instance, through the REST API: how often each ranking key puts a prediction with the right next event on top, by kind of data, by situation and by recall threshold. It also measures how well `future_potentials`, `ends_here` and `chance_posterior` state their own certainty, and what a prediction request costs.

It is written to be run against your own instance. It needs Python 3.9 or later and nothing else: no KATO import, no third-party package.

```bash
./start.sh start                                  # a KATO instance must be running

python -m benchmarks.ranking.run --suite smoke    # a couple of minutes, no downloads
python -m benchmarks.ranking.run                  # the guide suite: hours, not minutes
python -m benchmarks.ranking.report               # the docs page and the interactive report
```

A run's results go to `benchmarks/results/ranking/<name>/`. The report command builds `docs/reference/ranking-benchmark.md` from the guide run.

## What a Run Does

For each node of a suite, in order:

1. **Builds the data.** Generated data is computed; a public data set is downloaded the first time it is needed, checked against a pinned SHA-256, and read straight out of its archive.
2. **Loads the node.** It clears the node, then learns every sequence with `POST /sessions/{id}/observe-sequence`. Each learn is checked: the pattern name KATO returns must be the SHA-1 the client computes for the sequence. Afterwards the number of patterns KATO reports must equal the number of distinct sequences, and `finalize-training` is called.
3. **Asks the queries.** A query is an STM and the event that followed it. For each query and each recall threshold (0.1, 0.3, 0.5) it requests one response that holds every candidate, and reads from it what each of the 20 ranking keys would have put on top.
4. **Times requests.** Twenty requests, one at a time, with KATO's default `max_predictions`.
5. **Clears the node** and deletes its sessions.

### One Response Serves Every Key

KATO ranks by a fixed rule: highest value first, and among equal values the pattern name that sorts last (`kato.representations.prediction.rank_predictions`). A response with `max_predictions` at its maximum of 10,000 holds every candidate when the node has fewer patterns than that, so the client can apply the rule for each key itself. `tests/tests/unit/test_ranking_benchmark_live.py` checks this against a live service: KATO is asked for each key's own top, and the answers equal the client's reading of one full response.

When a response comes back full (10,000 predictions), the node has more candidates than one response carries. The run then asks KATO for each key separately, 100 predictions deep, and marks the record `capped`.

### What It Writes to Your Instance

Only nodes whose id is `<prefix>_<suite>_<node>`, by default `rankbench_guide_...` and `rankbench_smoke_...`. Each is cleared before it is loaded and again when its queries are done (`--keep-nodes` leaves them). No other node is read or written. Do not use a node prefix that starts with `test`, `topology_`, `perf_` or `load_test`: KATO's own test suite purges such nodes.

### Settings It Pins

So that two instances are compared on the same footing whatever their own defaults, every session sets: `use_token_matching` true, `fuzzy_token_threshold` 0.0, `filter_pipeline` empty, `max_pattern_length` 0, `stm_mode` CLEAR, `process_predictions` false. With no filter pipeline, every pattern above the recall threshold is a candidate.

## The Suites

**`smoke`**: two small generated nodes, 30 queries. It exercises every step and downloads nothing.

**`guide`**: 14 nodes, 30 query sets, 5,112 queries, 1.9 million events to learn.

| Node | Kind of data | Learns | Events | Patterns | Query sets |
|---|---|---:|---:|---:|---|
| `gen_base` | Generated | 12,000 | 244,159 | 1,957 | 9 situations and 1 of endings |
| `hdfs` | System logs | 8,216 | 159,392 | 1,282 | next event, endings |
| `msnbc` | Click streams | 6,270 | 42,489 | 3,107 | next event, endings |
| `wikitext` | Text | 3,985 | 104,151 | 3,967 | next event, endings |
| `bpi2012` | Finance | 6,544 | 129,930 | 2,383 | next event, endings |
| `sepsis` | Healthcare | 840 | 12,154 | 691 | next event, endings |
| `bach` | Music | 48 | 2,436 | 48 | next event, endings |
| `unix` | Computing | 4,119 | 93,060 | 3,065 | next event, endings |
| `gen_flat` | Generated | 12,000 | 293,766 | 2,952 | patterns learned equally often |
| `gen_skewed` | Generated | 12,000 | 221,445 | 611 | strongly skewed frequencies |
| `gen_multi` | Generated | 12,000 | 271,223 | 2,003 | events of 1 to 5 symbols |
| `gen_smallvocab` | Generated | 12,000 | 232,980 | 2,016 | a vocabulary of 50 symbols |
| `gen_stream_units` | Generated | 1,600 | 52,637 | 304 | a stream, boundaries given |
| `gen_stream_windows` | Generated | 5,263 | 52,630 | 2,683 | the same stream, boundaries not given |

A query set has 200 queries; a set of endings has 100 (12 for `bach`, which holds out 12 chorales). Every node is kept below 10,000 patterns, so one response always holds every candidate.

**Generated data** (`generated.py`) is a library of distinct sequences of 2 to 100 events, each a chain of shared motifs and fresh symbols, with Zipf-distributed symbols and pattern frequencies. The base setting has 1,000 symbols, 3,000 patterns, 5% noise and an STM of 5 events from the middle of a pattern; every other set changes one thing. It is produced by integer arithmetic on a SplitMix64 stream, so the same arguments give the same data on any machine and any Python. KATO itself uses no random numbers.

**The weights of `potential`** were fitted on generated data, system logs, click streams and text. Finance, healthcare, music and computing are kinds of data it never saw; the report gives them their own section.

## The Public Data Sets

Nothing is bundled with KATO. Each file is fetched from its original host when its node is about to load, kept in `benchmarks/ranking/data/` (git-ignored), and read as a stream: no archive is unpacked. The seven downloads come to about 195 MB, of which the HDFS archive is 187 MB.

| Data set | What a sequence is | Download | Licence |
|---|---|---:|---|
| [HDFS block traces](https://doi.org/10.5281/zenodo.8196385) (Loghub) | The log events of one HDFS block, as template ids | 186.6 MB | CC BY 4.0 on the Zenodo record; Loghub asks for research or academic use and a citation |
| [msnbc.com page visits](https://archive.ics.uci.edu/dataset/133/msnbc+com+anonymous+web+data) | The page categories one visitor requested in a day | 2.4 MB | CC BY 4.0 |
| [WikiText-2](https://arxiv.org/abs/1609.07843) | A sentence, one word per event | 2.4 MB | CC BY-SA |
| [BPI Challenge 2012](https://doi.org/10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f) | The handling of one loan application, step by step | 3.3 MB | [4TU General Terms of Use](https://doi.org/10.4121/resource:terms_of_use) |
| [Sepsis cases](https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460) | One patient's pathway through a hospital | 0.2 MB | [4TU General Terms of Use](https://doi.org/10.4121/resource:terms_of_use) |
| [Bach choral harmony](https://doi.org/10.24432/C5B61F) | The chord progression of one chorale | 0.04 MB | CC BY 4.0 |
| [UNIX user data](https://doi.org/10.24432/C5302K) | One shell session: commands, flags and metacharacters | 0.2 MB | CC BY 4.0 on the UCI page; see below |

**The UNIX user data carries stricter terms in its own README** than the licence shown on its UCI page: research use only, no literal tokens or token sequences published, and no part of it in a commercial product. The benchmark is built to stay inside them. It fetches the file from UCI at run time and redistributes nothing, and the result files hold counts and rates only, never a symbol. If those terms do not fit your use, leave the node out: `--only` with the other node names.

Every symbol is a token of its source with characters other than letters, digits and `_ . + -` percent-encoded, a one-to-one mapping. A learned sequence is cut to its first 100 events.

```bash
python -m benchmarks.ranking.run --check-data     # fetch, verify and read every data set, then stop
python -m benchmarks.ranking.run --discard-data   # delete each download once its node is done
```

## Results

```
benchmarks/results/ranking/<name>/run.json            what was run, on what, and each node's sizes and times
benchmarks/results/ranking/<name>/sets/<set>.jsonl    one line per query
```

`<name>` is the suite's name unless `--name` is given. A line of a set file:

| Field | Meaning |
|---|---|
| `i`, `q` | The query's index in its set, and a fingerprint of the query |
| `stm_events`, `stm_symbols`, `answer_symbols` | Sizes; `answer_symbols` is 0 when the sequence had ended |
| `t` | Per recall threshold: |
| `n`, `ms` | Predictions returned (the candidates), and the request's time during the accuracy pass |
| `top` | Per key: 2 the top prediction names the right event, 1 a wrong one, 0 none |
| `future` | The same for the top prediction that has a `future` |
| `rank` | Per key: rank of the first prediction that names the right event, 0 if none does |
| `tied` | Per key: how many predictions share the top value |
| `fp_p`, `fp_right`, `p_answer` | The top entry of `future_potentials`: its probability, whether it is right, and the probability given to the right event |
| `ends_here`, `chance` | As returned |
| `digest` | A fingerprint of every candidate's 20 values and of the ensemble figures, to the last bit |

No symbol of any data set is stored. The keys are in the order of `settings.keys` in `run.json`.

**A run can be continued.** Completed queries are never asked twice. Run the same command again after an interruption, or with a larger `--queries` to extend every set; the queries already stored stay as they are, because query `i` of a set is the same however many are drawn. A node that is not complete is loaded again from the start. `--fresh` deletes the run's results first.

**Two runs can be compared response by response**, by their fingerprints:

```bash
python -m benchmarks.ranking.report --compare benchmarks/results/ranking/guide /path/to/other/run
```

Two instances on the same KATO build must agree on every one. That is KATO's determinism, checked over the whole suite.

## The Reports

`python -m benchmarks.ranking.report` reads a run's files and writes, from the same figures:

- `docs/reference/ranking-benchmark.md`, with its charts as SVG files in `docs/reference/ranking-benchmark/`;
- `docs/reference/ranking-benchmark/report.html`, one self-contained interactive page: the recall threshold and the read-out can be switched, every mark shows its value on hover and on keyboard focus, and every chart has its table.

Both are generated; change `report.py`, not the pages. Text written by hand goes in `<run>/notes.md` and is placed under "Reading the Results". `--run` and `--out` choose another run and another place.

The guidance table at the top of the page follows one rule: in each case the best key is the one with the highest share of queries answered right, and a key is level with it when the 95% interval of the difference between the two, measured on the same queries, includes zero.

## Options

| Option | Default | |
|---|---|---|
| `--url` | `http://localhost:8000` | The instance |
| `--suite` | `guide` | `guide` or `smoke` |
| `--only NODE ...` | all | Run some of the suite's nodes |
| `--queries N` | 200 (12 for smoke) | Queries per set; sets of endings get half |
| `--concurrency N` | 4 | Sessions used at once, for learning and for queries. Match it to the service's worker count |
| `--name NAME` | the suite's name | Folder of this run under the results directory |
| `--node-prefix P` | `rankbench` | Start of the node ids the run writes |
| `--response-cap N` | 10000 | Predictions asked for per response; at or above it, each key is asked separately |
| `--check-data` | | Fetch, verify and read every data set, then stop. KATO is not needed |
| `--discard-data` | | Delete each download once its node is done |
| `--keep-nodes` | | Leave the nodes in KATO afterwards |
| `--note TEXT` | | A line shown at the top of the reports, for example the machine |
| `--fresh` | | Delete this run's stored results first |

## Tests

```bash
python -m pytest tests/tests/unit/test_ranking_benchmark.py        # in process
python -m pytest tests/tests/unit/test_ranking_benchmark_live.py   # needs a running service
```
