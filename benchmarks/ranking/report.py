"""Build the ranking benchmark's reports from a run's result files.

    python -m benchmarks.ranking.report                           # the guide run -> docs/reference/
    python -m benchmarks.ranking.report --run benchmarks/results/ranking/smoke --out /tmp/smoke-report
    python -m benchmarks.ranking.report --compare RUN_A RUN_B     # do two runs agree, response by response?

Writes, from the same figures:

    <out>/ranking-benchmark.md                  the docs page: tables, with the charts as SVG files
    <out>/ranking-benchmark/*.svg               the charts
    <out>/ranking-benchmark/report.html         one self-contained interactive page

Nothing is asked of KATO here: every figure is arithmetic on the stored
outcomes, so the reports can be rebuilt at any time and always agree with the
result files. The pages are generated; edit this module, not the pages. Notes
written by hand go in <run>/notes.md and are placed under "Reading the Results".
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from benchmarks.ranking import charts, stats

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_RUN = REPO / "benchmarks" / "results" / "ranking" / "guide"
DEFAULT_OUT = REPO / "docs" / "reference"
PAGE = "ranking-benchmark"

MEASURES = {
    "future": ("The top prediction that has a future",
               "Share of queries where the highest-ranked prediction that names a next event names the right one"),
    "top": ("The top prediction itself",
            "Share of queries where the highest-ranked prediction names the right next event"),
    "hit5": ("Among the first five predictions",
             "Share of queries where one of the five highest-ranked predictions names the right next event"),
}
ENTRY = "future_potentials, top entry"


# ----------------------------------------------------------------------------
# small formatting helpers

def f3(value) -> str:
    return "" if value is None else f"{value:.3f}"


def pct(value, digits: int = 1) -> str:
    return "" if value is None else f"{value * 100:.{digits}f}%"


def code(name: str) -> str:
    return f"`{name}`"


def span(share: dict) -> str:
    """'0.633 (0.612 to 0.654)'."""
    if share["p"] is None:
        return ""
    return f"{share['p']:.3f} ({share['lo']:.3f} to {share['hi']:.3f})"


def table(headers: list, rows: list, align: str = "") -> str:
    """A Markdown table. `align` gives 'l' or 'r' per column; default left then right."""
    align = align or "l" + "r" * (len(headers) - 1)
    rule = ["---" if a == "l" else "---:" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n</details>\n"


# ----------------------------------------------------------------------------
# the columns every per-key table uses

def kind_columns(run: dict) -> list:
    """Generated data as one column (the mean of its situations), then each public data set."""
    situations = [s["key"] for s in run["sets"].values() if s["group"] == "situation"]
    columns = []
    if situations:
        columns.append({"label": "Generated", "sets": situations, "in_fit": True})
    for query_set in run["sets"].values():
        if query_set["group"] == "data":
            columns.append({"label": query_set["kind"], "sets": [query_set["key"]], "in_fit": query_set["in_fit"],
                            "title": query_set["label"]})
    return columns


def situation_columns(run: dict) -> list:
    return [{"label": s["label"], "sets": [s["key"]]} for s in run["sets"].values() if s["group"] == "situation"]


def cell(run: dict, column: dict, threshold: str, measure: str, k) -> dict:
    """The share of one key (or of the top entry of future_potentials, k = None) in one column."""
    if k is None:
        return stats.mean_of_shares([stats.share(stats.entry_flags(run["sets"][key], threshold))
                                     for key in column["sets"]])
    return stats.case_share(run, column, threshold, measure, k)


def mean_cell(cells: list) -> dict:
    """The mean of a row's cells, each column counting the same."""
    known = [c for c in cells if c["p"] is not None]
    if not known:
        return {"p": None, "lo": None, "hi": None, "n": 0}
    m = len(known)
    p = sum(c["p"] for c in known) / m
    half = stats.Z * (sum(((c["hi"] - c["lo"]) / (2 * stats.Z)) ** 2 for c in known) ** 0.5) / m
    return {"p": p, "lo": max(0.0, p - half), "hi": min(1.0, p + half), "n": sum(c["n"] for c in known)}


def kinds_phrase(columns: list) -> str:
    return "Mean of 1 kind of data" if len(columns) == 1 else f"Mean of {len(columns)} kinds of data"


def key_order(run: dict, columns: list, threshold: str, measure: str) -> list:
    """Key indices, best first, by the mean over the columns."""
    means = {k: mean_cell([cell(run, c, threshold, measure, k) for c in columns])["p"] or 0.0
             for k in range(len(run["keys"]))}
    return sorted(means, key=lambda k: (-means[k], k))


# ----------------------------------------------------------------------------
# charts (each returns SVG text)

def chart_headline(run: dict, threshold: str, measure: str, standalone: bool) -> str:
    columns = kind_columns(run)
    rows = []
    for k in key_order(run, columns, threshold, measure):
        value = mean_cell([cell(run, c, threshold, measure, k) for c in columns])
        rows.append({"label": run["keys"][k], "value": value["p"], "lo": value["lo"], "hi": value["hi"],
                     "tip": f"{pct(value['p'])} ({pct(value['lo'])} to {pct(value['hi'])}) · {run['keys'][k]} · "
                            f"{kinds_phrase(columns).lower()}"})
    entry = mean_cell([cell(run, c, threshold, measure, None) for c in columns])
    rows.append({"label": ENTRY, "value": entry["p"], "lo": entry["lo"], "hi": entry["hi"], "quiet": True,
                 "tip": f"{pct(entry['p'])} ({pct(entry['lo'])} to {pct(entry['hi'])}) · {ENTRY} · "
                        f"the same for every ranking key"})
    return charts.ranked_bars(
        f"Share answered right, by ranking key: {MEASURES[measure][0].lower()}",
        f"{kinds_phrase(columns)}, recall_threshold {threshold}. Lines: 95% intervals. "
        f"Gray: a read-out that does not depend on the key.",
        rows, standalone)


def chart_grid(run: dict, columns: list, threshold: str, measure: str, title: str, mean_label: str,
               standalone: bool) -> str:
    """Conditions as rows, ranking keys as columns (best first), plus the top entry of future_potentials."""
    order = key_order(run, kind_columns(run), threshold, measure)
    labels = [ENTRY] + [run["keys"][k] for k in order]
    row_labels, values, tips = [], [], []
    for column in columns:
        cells = [cell(run, column, threshold, measure, None)] + [cell(run, column, threshold, measure, k) for k in order]
        row_labels.append(column["label"])
        values.append([c["p"] for c in cells])
        tips.append([f"{pct(c['p'])} ({pct(c['lo'])} to {pct(c['hi'])}) · {name} · {column['label']} · "
                     f"{c['n']} queries" for c, name in zip(cells, labels)])
    per_key = list(zip(*[[cell(run, c, threshold, measure, k) for c in columns] for k in [None] + order]))
    means = [mean_cell([row[i] for row in per_key]) for i in range(len(labels))] if per_key else []
    row_labels.append(mean_label)
    values.append([m["p"] for m in means])
    tips.append([f"{pct(m['p'])} ({pct(m['lo'])} to {pct(m['hi'])}) · {name} · {mean_label.lower()}"
                 for m, name in zip(means, labels)])
    return charts.grid(title, f"{MEASURES[measure][1]}, in percent. recall_threshold {threshold}.",
                       row_labels, labels, values, tips, standalone, row_breaks=(len(row_labels) - 1,),
                       column_breaks=(1,))


def top_outcomes(run: dict, column: dict, threshold: str, k: int) -> list:
    """[right, wrong, no future, no prediction] for a key's top prediction, as a mean over a column's sets."""
    parts = [[], [], [], []]
    for key in column["sets"]:
        entries = [row["t"][threshold] for row in run["sets"][key]["rows"]]
        n = len(entries)
        parts[0].append(sum(1 for e in entries if e["top"][k] == stats.RIGHT) / n)
        parts[1].append(sum(1 for e in entries if e["top"][k] not in (stats.RIGHT, stats.NO_EVENT)) / n)
        parts[2].append(sum(1 for e in entries if e["top"][k] == stats.NO_EVENT and e["n"] > 0) / n)
        parts[3].append(sum(1 for e in entries if e["n"] == 0) / n)
    return [sum(p) / len(p) for p in parts]


TOP_SERIES = [("s1", "names the right event"), ("s2", "names a wrong event"),
              ("quiet", "has no future"), ("quiet2", "no prediction at all")]


def chart_top(run: dict, threshold: str, standalone: bool) -> str:
    columns = kind_columns(run)
    rows = []
    for k in key_order(run, columns, threshold, "top"):
        by_column = [top_outcomes(run, c, threshold, k) for c in columns]
        parts = [sum(p[i] for p in by_column) / len(by_column) for i in range(4)]
        rows.append({"label": run["keys"][k], "parts": parts,
                     "tips": [f"{pct(part)} · {name} · {run['keys'][k]}" for part, (_, name) in zip(parts, TOP_SERIES)]})
    return charts.stacked_bars(
        "What the top prediction does, by ranking key",
        f"Share of queries, {kinds_phrase(columns).lower()}. recall_threshold {threshold}.",
        rows, TOP_SERIES, standalone)


FUTURE_SERIES = [("s1", "answered right"), ("s2", "answered wrong"),
                 ("quiet", "no prediction has a future"), ("quiet2", "no prediction at all")]


def future_outcomes(run: dict, column: dict, threshold: str, k: int) -> list:
    parts = [[], [], [], []]
    for key in column["sets"]:
        entries = [row["t"][threshold] for row in run["sets"][key]["rows"]]
        n = len(entries)
        parts[0].append(sum(1 for e in entries if e["future"][k] == stats.RIGHT) / n)
        parts[1].append(sum(1 for e in entries if e["future"][k] not in (stats.RIGHT, stats.NO_EVENT)) / n)
        parts[2].append(sum(1 for e in entries if e["future"][k] == stats.NO_EVENT and e["n"] > 0) / n)
        parts[3].append(sum(1 for e in entries if e["n"] == 0) / n)
    return [sum(p) / len(p) for p in parts]


def chart_thresholds(run: dict, key_name: str, standalone: bool) -> str:
    k = run["keys"].index(key_name)
    rows = []
    for column in kind_columns(run):
        for i, threshold in enumerate(run["thresholds"]):
            parts = future_outcomes(run, column, threshold, k)
            rows.append({"label": f"{column['label']}, {threshold}", "parts": parts, "gap_before": i == 0 and bool(rows),
                         "tips": [f"{pct(part)} · {name} · {column['label']} · recall_threshold {threshold}"
                                  for part, (_, name) in zip(parts, FUTURE_SERIES)]})
    return charts.stacked_bars(
        f"What a higher recall_threshold does, ranked by {key_name}",
        "Share of queries by outcome of the top prediction that has a future, at each threshold.",
        rows, FUTURE_SERIES, standalone)


def transfer_rows(run: dict, threshold: str = stats.GUIDE_THRESHOLD) -> list:
    """`potential` against the best other key, data set by data set."""
    keys = run["keys"]
    if "potential" not in keys:
        return []
    p = keys.index("potential")
    out = []
    for query_set in run["sets"].values():
        if query_set["group"] != "data":
            continue
        case = {"sets": [query_set["key"]]}
        shares = [stats.case_share(run, case, threshold, "future", k) for k in range(len(keys))]
        other = max((k for k in range(len(keys)) if k != p), key=lambda k: (shares[k]["p"], -k))
        difference = stats.case_difference(run, case, threshold, "future", p, other)
        low, high = stats.interval(difference)
        out.append({"label": query_set["kind"], "title": query_set["label"], "in_fit": query_set["in_fit"],
                    "potential": shares[p], "other": keys[other], "other_share": shares[other],
                    "difference": difference["d"], "lo": low, "hi": high, "queries": difference["n"],
                    "verdict": "level" if low <= 0 <= high else ("ahead" if difference["d"] > 0 else "behind")})
    out.sort(key=lambda row: not row["in_fit"])
    return out


def chart_transfer(run: dict, standalone: bool) -> str:
    rows = transfer_rows(run)
    if not rows:
        return ""
    bars = []
    for i, row in enumerate(rows):
        fitted = "fitted on" if row["in_fit"] else "never seen"
        bars.append({"label": f"{row['label']} ({fitted})", "value": row["difference"] * 100,
                     "lo": row["lo"] * 100, "hi": row["hi"] * 100,
                     "gap_before": i > 0 and row["in_fit"] != rows[i - 1]["in_fit"],
                     "tip": f"{row['difference'] * 100:+.1f} points ({row['lo'] * 100:+.1f} to {row['hi'] * 100:+.1f}) · "
                            f"potential {pct(row['potential']['p'])} against {row['other']} "
                            f"{pct(row['other_share']['p'])} · {row['title']}"})
    return charts.diverging_bars(
        "potential against the best other key, data set by data set",
        "Difference in the share answered right, in points, on the same queries. Lines: 95% intervals.",
        bars, "points", standalone)


def pooled_sets(run: dict) -> list:
    return [s for s in run["sets"].values() if s["group"] in ("data", "situation")]


def chart_calibration(run: dict, threshold: str, standalone: bool) -> str:
    figures = stats.calibration(pooled_sets(run), threshold)
    points = [{"stated": b["stated"], "right": b["right"], "n": b["n"],
               "tip": f"{pct(b['right'])} right where {pct(b['stated'])} was stated · {b['n']} answers"}
              for b in figures["bins"] if b["n"]]
    return charts.calibration_line(
        "future_potentials: the probability stated against how often the top entry is right",
        f"Every next-event query, in ten bins of stated probability. recall_threshold {threshold}.",
        points, standalone)


def pooled_histograms(pairs: list) -> tuple:
    bins = len(pairs[0]["ended"]["histogram"]) if pairs else 10
    ended = [sum(pair["ended"]["histogram"][b] for pair in pairs) for b in range(bins)]
    went_on = [sum(pair["went_on"]["histogram"][b] for pair in pairs) for b in range(bins)]
    return ended, went_on


def chart_endings(run: dict, threshold: str, standalone: bool) -> str:
    pairs = stats.endings(run, threshold)
    ended, went_on = pooled_histograms(pairs)
    categories = [f"{b * 10}–{b * 10 + 10}" for b in range(len(ended))]

    def series(name, cls, counts):
        total = sum(counts) or 1
        return {"name": name, "class": cls, "values": [c / total for c in counts],
                "tips": [f"{pct(c / total)} of the queries where {name} ({c} of {total}) · ends_here {label}%"
                         for c, label in zip(counts, categories)]}

    return charts.grouped_columns(
        "ends_here where the sequence ended and where it went on",
        f"Share of each group's queries by the value of ends_here. recall_threshold {threshold}.",
        categories, [series("the sequence ended", "s1", ended), series("the sequence went on", "s2", went_on)],
        "ends_here, %", standalone)


def chart_latency(run: dict, standalone: bool) -> str:
    figures = stats.latency(run)
    points = [{"x": p["candidates"], "y": p["ms"],
               "tip": f"{p['ms']:.0f} ms · {p['candidates']:,} candidates · {p['node']}"} for p in figures["points"]]
    return charts.scatter(
        "Time of one prediction request against its number of candidates",
        "One dot per request, asked one at a time with max_predictions 100. Every node of the suite.",
        points, "Candidates above the recall threshold", "Milliseconds", standalone)


# ----------------------------------------------------------------------------
# tables (each returns Markdown)

def guide_rows(run: dict) -> tuple:
    """The rows of the guidance table and, per key, the number of cases it is best or level in."""
    keys = run["keys"]
    rows, counts = [], {key: {"best": 0, "level": 0} for key in keys}
    one_by_one = stats.cases(run)
    for case in stats.groups(run) + one_by_one:
        result = stats.verdict(run, case)
        best = [keys[k] for k in result["best"]]
        level_with = [keys[k] for k in result["level"]]
        queries = sum(len(run["sets"][key]["rows"]) for key in case["sets"])
        rows.append({"label": case["label"], "kind": case.get("kind", ""), "group": case.get("group", "group"),
                     "queries": queries, "best": best, "level": level_with,
                     "share": result["shares"][result["best"][0]]})
        if case in one_by_one:
            for name in best:
                counts[name]["best"] += 1
            for name in level_with:
                counts[name]["level"] += 1
    return rows, counts, len(one_by_one)


def table_guide(rows: list) -> str:
    def body(selected):
        return table(
            ["Case", "Queries", "Best key", "Share right", "Level with the best"],
            [[row["label"] if row["group"] != "data" else f"{row['kind']}: {row['label']}", row["queries"],
              ", ".join(code(name) for name in row["best"]), f3(row["share"]["p"]),
              ", ".join(code(name) for name in row["level"]) or "none"] for row in selected], "lrlrl")
    out = ""
    for heading, group in (("Groups of cases", "group"), ("Public data sets", "data"),
                           ("Generated data, one condition at a time", "situation")):
        selected = [row for row in rows if row["group"] == group]
        if selected:
            out += f"**{heading}**\n\n" + body(selected) + "\n"
    return out


def table_counts(run: dict, counts: dict, total: int) -> str:
    order = sorted(run["keys"], key=lambda name: (-(counts[name]["best"] + counts[name]["level"]),
                                                  -counts[name]["best"], run["keys"].index(name)))
    return table(["Ranking key", "Best", "Level with the best", f"Best or level, of {total} cases"],
                 [[code(name), counts[name]["best"], counts[name]["level"],
                   counts[name]["best"] + counts[name]["level"]] for name in order])


def table_keys(run: dict, columns: list, threshold: str, measure: str, mean_label: str = "Mean") -> str:
    """Ranking keys as rows, conditions as columns."""
    order = key_order(run, kind_columns(run), threshold, measure)
    rows = []
    for k in [None] + order:
        cells = [cell(run, c, threshold, measure, k) for c in columns]
        name = f"*{ENTRY}*" if k is None else code(run["keys"][k])
        rows.append([name, f3(mean_cell(cells)["p"])] + [f3(c["p"]) for c in cells])
    return table(["Ranking key", mean_label] + [c["label"] for c in columns], rows)


def table_headline(run: dict, threshold: str) -> str:
    columns = kind_columns(run)
    rows = []
    for k in key_order(run, columns, threshold, "future"):
        value = mean_cell([cell(run, c, threshold, "future", k) for c in columns])
        tied = stats.mean_of_shares([
            stats.mean_of_shares([stats.key_figures(run["sets"][key], threshold, k)["tied"] for key in c["sets"]])
            for c in columns])
        rows.append([code(run["keys"][k]), span(value), pct(tied["p"])])
    entry = mean_cell([cell(run, c, threshold, "future", None) for c in columns])
    rows.append([f"*{ENTRY}*", span(entry), ""])
    return table(["Ranking key", "Share answered right (95% interval)", "Queries with a tie for first place"], rows)


def table_top(run: dict, threshold: str) -> str:
    columns = kind_columns(run)

    def mean_over_kinds(figures: list, field: str) -> str:
        return f3(mean_cell([stats.mean_of_shares([f[field] for f in column]) for column in figures])["p"])

    rows = []
    for k in key_order(run, columns, threshold, "top"):
        figures = [[stats.key_figures(run["sets"][key], threshold, k) for key in c["sets"]] for c in columns]
        mrr = sum(sum(f["mrr"] for f in column) / len(column) for column in figures) / len(figures)
        rows.append([code(run["keys"][k])]
                    + [mean_over_kinds(figures, field) for field in ("top", "precision", "named", "future", "hit5")]
                    + [f3(mrr)])
    return table(["Ranking key", "Accuracy", "Precision", "Names an event", "Top with a future",
                  "Among the first five", "Mean reciprocal rank"], rows)


def table_thresholds(run: dict) -> str:
    columns = kind_columns(run)
    rows = []
    for k in key_order(run, columns, run["thresholds"][0], "future"):
        rows.append([code(run["keys"][k])] + [
            f3(mean_cell([cell(run, c, t, "future", k) for c in columns])["p"]) for t in run["thresholds"]])
    rows.append([f"*{ENTRY}*"] + [f3(mean_cell([cell(run, c, t, "future", None) for c in columns])["p"])
                                  for t in run["thresholds"]])
    return table(["Ranking key"] + [f"recall_threshold {t}" for t in run["thresholds"]], rows)


def table_threshold_cost(run: dict) -> str:
    rows = []
    for column in kind_columns(run):
        row = [column["label"]]
        for threshold in run["thresholds"]:
            figures = [stats.set_figures(run["sets"][key], threshold) for key in column["sets"]]
            row.append(f"{sum(f['candidates'] for f in figures) / len(figures):,.0f}")
        for threshold in run["thresholds"]:
            figures = [stats.set_figures(run["sets"][key], threshold) for key in column["sets"]]
            row.append(pct(stats.mean_of_shares([f["empty"] for f in figures])["p"]))
        for threshold in run["thresholds"]:
            figures = [stats.set_figures(run["sets"][key], threshold) for key in column["sets"]]
            row.append(pct(stats.mean_of_shares([f["oracle"] for f in figures])["p"]))
        rows.append(row)
    thresholds = run["thresholds"]
    return table(["Kind of data"] + [f"Candidates at {t}" for t in thresholds]
                 + [f"No prediction at {t}" for t in thresholds]
                 + [f"Some prediction right at {t}" for t in thresholds], rows)


def table_transfer(run: dict) -> str:
    rows = [[f"{row['label']}: {row['title']}", "fitted on" if row["in_fit"] else "never seen", row["queries"],
             f3(row["potential"]["p"]), f"{code(row['other'])} {f3(row['other_share']['p'])}",
             f"{row['difference'] * 100:+.1f} ({row['lo'] * 100:+.1f} to {row['hi'] * 100:+.1f})", row["verdict"]]
            for row in transfer_rows(run)]
    return table(["Data set", "When the weights were fitted", "Queries", "`potential`", "Best other key",
                  "Difference in points (95% interval)", "`potential` is"], rows, "llrrlrl")


def table_calibration(run: dict, threshold: str) -> str:
    columns = kind_columns(run) + [{"label": "All", "sets": [s["key"] for s in pooled_sets(run)]}]
    figures = [stats.calibration([run["sets"][key] for key in c["sets"]], threshold) for c in columns]
    lines = [
        ["Queries with an entry"] + [f["answers"] for f in figures],
        ["Probability stated, on average"] + [f3(f["stated"]) for f in figures],
        ["Share of the top entries that were right"] + [f3(f["right"]) for f in figures],
        ["Mean gap between stated and observed"] + [f3(f["gap"]) for f in figures],
        ["Area under the ROC curve"] + [f3(f["auroc"]) for f in figures],
        ["Answers with a probability of 0.9 or more"] + [pct(f["at"]["0.9"]["share"], 0) for f in figures],
        ["Right among those"] + [pct(f["at"]["0.9"]["right"]["p"], 0) for f in figures],
        ["Answers with a probability of 0.5 or more"] + [pct(f["at"]["0.5"]["share"], 0) for f in figures],
        ["Right among those"] + [pct(f["at"]["0.5"]["right"]["p"], 0) for f in figures],
        ["Right among the most confident quarter"] + [pct(f["top_quarter_right"], 0) for f in figures],
    ]
    return table([""] + [c["label"] for c in columns], lines)


def table_endings(run: dict, threshold: str) -> str:
    rows = []
    for pair in stats.endings(run, threshold):
        rows.append([pair["kind"] if pair["kind"] != "Generated" else "Generated",
                     pair["ended"]["n"], f3(pair["ended"]["mean"]), f3(pair["went_on"]["mean"]),
                     pct(pair["ended"]["above_half"]["p"], 0), pct(pair["went_on"]["above_half"]["p"], 0),
                     pct(pair["ended"]["says_end"]["p"], 0), pct(pair["went_on"]["says_end"]["p"], 0),
                     f3(pair["auroc"])])
    return table(["Kind of data", "Endings asked", "`ends_here`, ended", "`ends_here`, went on",
                  "Above 0.5, ended", "Above 0.5, went on", "Above the top entry, ended",
                  "Above the top entry, went on", "Area under the ROC curve"], rows)


def table_no_future(run: dict, threshold: str) -> str:
    rows = stats.no_future_shares(run, threshold)
    rows.sort(key=lambda row: -((row["ended"]["p"] or 0) - (row["went_on"]["p"] or 0)))
    return table(["Ranking key", "Top prediction has no future: the sequence ended", "The sequence went on",
                  "Difference in points"],
                 [[code(row["key"]), pct(row["ended"]["p"]), pct(row["went_on"]["p"]),
                   f"{((row['ended']['p'] or 0) - (row['went_on']['p'] or 0)) * 100:+.1f}"] for row in rows])


def table_chance(run: dict, threshold: str) -> str:
    columns = kind_columns(run)
    figures = [stats.chance([run["sets"][key] for key in c["sets"]], threshold) for c in columns]
    lines = [
        ["Queries with `chance_posterior` above 0.5"] + [pct(f["share"]) for f in figures],
        ["Top entry right, among those"] + [
            pct(f["right_inside"]["p"], 0) if f["right_inside"]["n"] >= 20 else "too few" for f in figures],
        ["Top entry right, among the other queries"] + [pct(f["right_outside"]["p"], 0) for f in figures],
    ]
    return table([""] + [c["label"] for c in columns], lines)


def table_latency(run: dict) -> str:
    figures = stats.latency(run)
    return table(["Node", "Patterns", "Candidates, median", "Request time, median", "90th percentile"],
                 [[row["label"], f"{row['patterns']:,}", f"{row['candidates']:,.0f}", f"{row['ms']:,.0f} ms",
                   f"{row['ms_p90']:,.0f} ms"] for row in figures["nodes"]])


def table_latency_keys(run: dict) -> str:
    nodes = [row for row in stats.latency(run)["nodes"] if row["by_key"]]
    if not nodes:
        return ""
    return table(["Ranking key"] + [f"{row['label']}, median" for row in nodes],
                 [[code(key)] + [f"{row['by_key'][key]:,.0f} ms" for row in nodes] for key in run["keys"]])


def table_nodes(run: dict) -> str:
    rows = []
    for node_key in run["record"].get("node_order") or sorted(run["record"]["nodes"]):
        node = run["record"]["nodes"].get(node_key)
        if not node or "sets" not in node:
            continue
        queries = sum(info["queries"] for info in node["sets"].values())
        rows.append([node["label"], node["kind"], f"{node['learned_sequences']:,}", f"{node['events']:,}",
                     f"{node['patterns']:,}", f"{node['vocabulary']:,}", queries])
    return table(["Node", "Kind of data", "Sequences learned", "Events", "Patterns", "Symbols", "Queries"], rows,
                 "llrrrrr")


def table_sources(run: dict) -> str:
    rows = []
    for source in run["record"].get("sources", {}).values():
        rows.append([f"[{source['title']}]({source['page']})", source["kind"], source["what"], source["licence"],
                     source["cite"]])
    return table(["Data set", "Kind", "What a sequence is", "Licence", "Source"], rows, "lllll")


# ----------------------------------------------------------------------------
# the docs page

def sentences(run: dict, counts: dict, total: int) -> list:
    """Statements read off the figures by fixed rules. No judgement is added here."""
    keys = run["keys"]
    order = sorted(keys, key=lambda name: -(counts[name]["best"] + counts[name]["level"]))
    lead = order[0]
    out = [f"{code(lead)} is the best key, or level with the best, in "
           f"{counts[lead]['best'] + counts[lead]['level']} of the {total} cases."]
    others = [name for name in order[1:4]]
    if others:
        out.append("Next: " + ", ".join(
            f"{code(name)} ({counts[name]['best'] + counts[name]['level']})" for name in others) + ".")
    rows = transfer_rows(run)
    unseen = [row for row in rows if not row["in_fit"]]
    if unseen:
        tally = {verdict: sum(1 for row in unseen if row["verdict"] == verdict) for verdict in ("ahead", "level", "behind")}
        out.append(
            f"On the {len(unseen)} kinds of data {code('potential')} never saw when its weights were fitted, it is "
            f"ahead of the best other key on {tally['ahead']}, level on {tally['level']} and behind on {tally['behind']}.")
    return out


def build_markdown(run: dict, images: str) -> str:
    """The docs page. `images` is the folder of the SVG files, relative to the page."""
    record = run["record"]
    threshold = stats.GUIDE_THRESHOLD
    rows, counts, total = guide_rows(run)
    queries = sum(len(s["rows"]) for s in run["sets"].values())
    run_path = Path(run["dir"])
    try:
        run_link = "../../" + str(run_path.resolve().relative_to(REPO)) + "/run.json"
    except ValueError:
        run_link = str(run_path / "run.json")
    notes_path = run_path / "notes.md"
    notes = notes_path.read_text().strip() if notes_path.exists() else ""
    kinds = kind_columns(run)
    unseen = [c["label"] for c in kinds if not c.get("in_fit", True)]
    note = f"\n**Note.** {record['note']}\n" if record.get("note") else ""

    def image(name: str, alt: str) -> str:
        return f"![{alt}]({images}/{name}.svg)\n"

    parts = [f"""# Ranking Benchmark: Which `rank_sort_algo` to Use

How often each ranking key puts the right next event on top, measured through the REST API of a running KATO instance: {queries:,} held-out queries on {len(record['nodes'])} nodes, {len(run['keys'])} ranking keys, recall thresholds {', '.join(run['thresholds'])}.
{note}
> This page is generated by `python -m benchmarks.ranking.report` from the result files of one run. Do not edit it by hand. The instance, the machine and the date of the run are in [`run.json`]({run_link}). To measure your own instance, see [Reproducing](#reproducing).

For what each metric is and how it is computed, see the [Prediction Object Reference](prediction-object.md).

## At a Glance

{' '.join(sentences(run, counts, total))}

The table follows one rule, fixed before the run. In each case the best key is the one with the highest share of queries answered right. A key is **level** with it when the 95% interval of the difference between the two, measured on the same queries, includes zero. Read-out: the top-ranked prediction that has a `future`. `recall_threshold` {threshold}.

{table_guide(rows)}
How often each key is best or level, over the {total} single cases (groups not counted):

{table_counts(run, counts, total)}
{image('headline', 'Share answered right by ranking key')}
{details('Table', table_headline(run, threshold))}
"""]
    if notes:
        parts.append(f"## Reading the Results\n\n{notes}\n")

    parts.append(f"""## How It Was Measured

1. **The task.** Next-event prediction. A query is a stretch of a sequence the node has not learned, taken as the STM, together with the event that followed it. An answer is right when the predicted next event is exactly that event.
2. **The nodes.** Each node learns one data set through `POST /sessions/{{id}}/observe-sequence`, one sequence per pattern, and `finalize-training` is called before the queries. A learned sequence is cut to its first 100 events. Every node is checked after loading: the pattern name KATO returns for each sequence, and the number of patterns it reports.
3. **The data.** Generated sequence libraries that change one condition at a time, and public data sets. The weights of `potential` were fitted on generated data, system logs, click streams and text{'; ' + ', '.join(unseen).lower() + ' are kinds of data it never saw' if unseen else ''}.
4. **The queries.** On a public data set, a position is drawn uniformly from the held-out sequences; the STM is the five events before it, or fewer when fewer came before, and never less than two. On generated data the query follows the condition named. For each node a second set asks about sequences that have ended: the STM is the last five events of a complete held-out sequence, and nothing follows.
5. **The settings.** Token-level matching, fuzzy matching off, no filter pipeline, so every pattern above the recall threshold is a candidate. One response with `max_predictions` at its maximum holds every candidate, and the client ranks it by each key with KATO's own rule: highest value first, and among equal values the pattern name that sorts last.
6. **The read-outs.** *The top prediction that has a future*: the highest-ranked prediction whose `future` is not empty. *The top prediction itself*: the highest-ranked prediction, which names no event when its pattern ends where the STM ends. *The top entry of `future_potentials`*: the most probable next event over all candidates; it does not depend on the ranking key.
7. **The figures.** A share is a count of queries over a count of queries. For a group, it is the mean over the group's query sets, each set counting the same; "mean of the kinds" counts each kind of data once. Intervals are 95%: Wilson for one share, normal for a mean and for a difference on the same queries. With 200 queries, a share of 0.5 has an interval of about ±0.07.

{table_nodes(run)}""")
    if record.get("sources"):
        parts.append(table_sources(run))

    parts.append(f"""## By Kind of Data

{image('kinds', 'Share answered right by kind of data and ranking key')}
{details('Table', table_keys(run, kinds, threshold, 'future', 'Mean of the kinds'))}""")
    if transfer_rows(run):
        parts.append(f"""### Data `potential` Never Saw

The weights of `potential` are constants fitted once. This is the test of whether they carry over: on each public data set, `potential` against the best of the other {len(run['keys']) - 1} keys on that data set, on the same queries. The other key is chosen after the fact, which favours it.

{image('transfer', 'potential against the best other key on each data set')}
{table_transfer(run)}""")
    if situation_columns(run):
        parts.append(f"""## By Situation

Generated data, one condition changed at a time.

{image('situations', 'Share answered right by situation and ranking key')}
{details('Table', table_keys(run, situation_columns(run), threshold, 'future', 'Mean'))}""")

    parts.append(f"""## The Top Prediction Itself

The top-ranked prediction can be a pattern that ends where the STM ends. Its `future` is empty and it names no next event. Accuracy is the share of all queries the top prediction gets right, precision the share it gets right of those where it names an event. The last three columns look further down the list.

{image('top', 'What the top prediction does, by ranking key')}
{table_top(run, threshold)}
## Recall Threshold

A higher `recall_threshold` leaves fewer candidates. Share answered right by the top prediction that has a future, mean of the kinds:

{table_thresholds(run)}
{image('thresholds', 'Outcome of the top prediction at each recall threshold')}
What the threshold costs and what it removes: candidates per request, queries with no prediction at all (KATO's "I don't know"), and queries where at least one prediction names the right event.

{table_threshold_cost(run)}
## How Sure: `future_potentials`

The `probability` of the top entry, against how often that entry is right.

{image('calibration', 'Probability stated by future_potentials against the share right')}
{table_calibration(run, threshold)}""")
    if stats.endings(run, threshold):
        parts.append(f"""## When the Sequence Has Ended: `ends_here`

`ends_here` is the probability that no event follows. Here it is measured both ways: on queries where an event did follow, and on complete sequences observed to their last event.

{image('endings', 'ends_here where the sequence ended and where it went on')}
{table_endings(run, threshold)}
"Above the top entry" means `ends_here` is larger than the probability of the most probable next event, or no next event is proposed.

The ranking key decides how often the top prediction is a pattern that has ended. Where the sequence ended that is the right reading; where it went on, the top prediction names no event.

{table_no_future(run, threshold)}""")
    parts.append(f"""## How Sure: `chance_posterior`

{table_chance(run, threshold)}""")
    if stats.latency(run)["points"]:
        parts.append(f"""## Request Time

Times are from the machine recorded in [`run.json`]({run_link}): one request at a time, `max_predictions` 100, `recall_threshold` {threshold}. They depend on the hardware; compare them with a run of your own.

{image('latency', 'Request time against the number of candidates')}
{table_latency(run)}
Every metric is computed for every candidate whichever key ranks them, so the key does not change the time:

{table_latency_keys(run)}""")
    parts.append(f"""## What Was Not Measured

- **The affinity-weighted metrics.** They are deprecated, and the data sets carry no emotives.
- **Fuzzy token matching**, character-level matching and a configured filter pipeline.
- **STMs of one symbol.** Every query has at least two.
- **Vectors and emotives.** Every event is one or more string symbols.
- **Nodes of more than 10,000 patterns.** The suite keeps each node below what one response can carry.
- **Other domains.** {len(kinds)} kinds of data are not all kinds. The figures say how the keys behave on these.

## Reproducing

```bash
./start.sh start                                  # a KATO instance must be running
python -m benchmarks.ranking.run --suite smoke    # two minutes, no downloads
python -m benchmarks.ranking.run                  # the guide suite
python -m benchmarks.ranking.report               # this page and the interactive report
```

The run writes only to nodes named `rankbench_...` and clears each when its queries are done. Every response is stored with a fingerprint of all its candidates' values, so two runs can be compared response by response:

```bash
python -m benchmarks.ranking.report --compare benchmarks/results/ranking/guide path/to/another/run
```

See [benchmarks/ranking/README.md](../../benchmarks/ranking/README.md) for the options, the data sets and their licences.
""")
    return "\n".join(parts)


def build_charts(run: dict, threshold: str, standalone: bool) -> dict:
    """The charts of the docs page, by file name. A chart whose data the run lacks is left out."""
    out = {
        "headline": chart_headline(run, threshold, "future", standalone),
        "kinds": chart_grid(run, kind_columns(run), threshold, "future",
                            "Share answered right, by kind of data and ranking key", "Mean of the kinds", standalone),
        "top": chart_top(run, threshold, standalone),
        "thresholds": chart_thresholds(run, "potential" if "potential" in run["keys"] else run["keys"][0], standalone),
        "calibration": chart_calibration(run, threshold, standalone),
    }
    if transfer_rows(run):
        out["transfer"] = chart_transfer(run, standalone)
    if stats.endings(run, threshold):
        out["endings"] = chart_endings(run, threshold, standalone)
    if situation_columns(run):
        out["situations"] = chart_grid(run, situation_columns(run), threshold, "future",
                                       "Share answered right, by situation and ranking key", "Mean", standalone)
    if stats.latency(run)["points"]:
        out["latency"] = chart_latency(run, standalone)
    return out


# ----------------------------------------------------------------------------
# the interactive page

def code_html(text: str) -> str:
    """Escaped text with `code` spans turned into <code>."""
    out = html.escape(text)
    while out.count("`") >= 2:
        out = out.replace("`", "<code>", 1).replace("`", "</code>", 1)
    return out


def md_table_to_html(markdown: str) -> str:
    """A Markdown table (as `table` writes it) as an HTML table. Cells are escaped; `code` and *emphasis* kept."""
    lines = [line for line in markdown.strip().splitlines() if line.startswith("|")]
    if len(lines) < 2:
        return ""

    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def inline(text):
        text = html.escape(text)
        while "`" in text and text.count("`") >= 2:
            text = text.replace("`", "<code>", 1).replace("`", "</code>", 1)
        if text.startswith("*") and text.endswith("*") and len(text) > 2:
            text = f"<em>{text[1:-1]}</em>"
        if text.startswith("[") and "](" in text and text.endswith(")"):
            label, link = text[1:].split("](", 1)
            if link[:-1].startswith("https://"):
                text = f'<a href="{link[:-1]}">{label}</a>'
        return text

    aligns = ["right" if c.endswith(":") else "left" for c in cells(lines[1])]
    head = "".join(f'<th style="text-align:{a}">{inline(c)}</th>' for c, a in zip(cells(lines[0]), aligns))
    body = "".join(
        "<tr>" + "".join(f'<td style="text-align:{a}">{inline(c)}</td>' for c, a in zip(cells(line), aligns)) + "</tr>"
        for line in lines[2:])
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


PAGE_CSS = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 15px; line-height: 1.5; }
.viz-root { background: var(--kz-page); color: var(--kz-ink); min-height: 100vh; }
.viz-root { --kz-page: #f9f9f7; --kz-border: rgba(11,11,11,0.10); }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .viz-root { --kz-page: #0d0d0d; --kz-border: rgba(255,255,255,0.10); } }
:root[data-theme="dark"] .viz-root { --kz-page: #0d0d0d; --kz-border: rgba(255,255,255,0.10); }
main { max-width: 1040px; margin: 0 auto; padding: 24px 20px 64px; }
h1 { font-size: 26px; line-height: 1.25; margin: 8px 0 8px; }
h2 { font-size: 19px; margin: 40px 0 8px; }
h3 { font-size: 16px; margin: 28px 0 8px; }
p { margin: 8px 0; max-width: 78ch; color: var(--kz-ink2); }
p strong, li strong { color: var(--kz-ink); }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.92em; }
a { color: inherit; }
.lede { font-size: 16px; }
.filters { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center;
  padding: 10px 14px; margin: 20px 0 8px; background: var(--kz-surface); border: 1px solid var(--kz-border); border-radius: 10px; }
.filters fieldset { border: 0; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.filters legend { float: left; padding: 0 8px 0 0; font-size: 13px; color: var(--kz-ink2); }
.filters label { font-size: 13px; padding: 4px 10px; border: 1px solid var(--kz-border); border-radius: 999px; cursor: pointer; }
.filters input { position: absolute; opacity: 0; pointer-events: none; }
.filters input:checked + span { font-weight: 600; }
.filters label:has(input:checked) { background: var(--kz-ink); color: var(--kz-surface); border-color: var(--kz-ink); }
.filters label:has(input:focus-visible) { outline: 2px solid var(--kz-s1); outline-offset: 2px; }
.theme { margin-left: auto; font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 999px; cursor: pointer;
  background: transparent; color: var(--kz-ink); border: 1px solid var(--kz-border); }
figure { margin: 16px 0; padding: 0; }
figure > .scroll { overflow-x: auto; border-radius: 8px; }
figure svg { display: block; max-width: none; }
.kz [data-tip] { cursor: default; }
.kz [data-tip]:hover { filter: brightness(1.12) saturate(1.05); }
.kz [data-tip]:focus { outline: none; }
.kz [data-tip]:focus-visible { outline: 2px solid var(--kz-ink); outline-offset: 1px; }
details { margin: 8px 0 16px; }
summary { cursor: pointer; font-size: 13px; color: var(--kz-ink2); width: max-content; padding: 2px 0; }
.table-wrap { overflow-x: auto; margin: 8px 0 16px; border: 1px solid var(--kz-border); border-radius: 8px; background: var(--kz-surface); }
table { border-collapse: collapse; font-size: 13px; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--kz-grid); white-space: nowrap; }
td:first-child, th:first-child { white-space: normal; min-width: 180px; }
th { font-weight: 600; color: var(--kz-ink); background: var(--kz-surface); }
tbody tr:last-child td { border-bottom: 0; }
td { color: var(--kz-ink2); }
#tip { position: fixed; z-index: 20; pointer-events: none; max-width: 340px; padding: 7px 10px; border-radius: 8px;
  font-size: 12.5px; line-height: 1.4; background: var(--kz-ink); color: var(--kz-surface); box-shadow: 0 4px 16px rgba(0,0,0,0.25); }
#tip b { font-weight: 600; font-size: 13.5px; display: block; }
#tip[hidden] { display: none; }
[hidden] { display: none !important; }
.note { font-size: 13px; color: var(--kz-muted); }
"""

PAGE_JS = """
(function () {
  var root = document.documentElement, tip = document.getElementById('tip');
  function apply() {
    var t = document.querySelector('input[name=threshold]:checked').value;
    var m = document.querySelector('input[name=measure]:checked').value;
    document.querySelectorAll('[data-threshold]').forEach(function (el) {
      var ok = el.getAttribute('data-threshold') === t;
      if (ok && el.hasAttribute('data-measure')) ok = el.getAttribute('data-measure') === m;
      el.hidden = !ok;
    });
  }
  document.querySelectorAll('.filters input').forEach(function (el) { el.addEventListener('change', apply); });
  apply();
  function show(el, x, y) {
    var text = el.getAttribute('data-tip') || '', cut = text.indexOf(' · ');
    tip.textContent = '';
    var lead = document.createElement('b');
    lead.textContent = cut < 0 ? text : text.slice(0, cut);
    tip.appendChild(lead);
    if (cut >= 0) tip.appendChild(document.createTextNode(text.slice(cut + 3)));
    tip.hidden = false;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x + 14)) + 'px';
    tip.style.top = Math.max(8, y - h - 12 < 8 ? y + 18 : y - h - 12) + 'px';
  }
  document.addEventListener('pointermove', function (e) {
    var el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (el) show(el, e.clientX, e.clientY); else tip.hidden = true;
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el) return;
    var box = el.getBoundingClientRect();
    show(el, box.left + box.width / 2, box.top);
  });
  document.addEventListener('focusout', function () { tip.hidden = true; });
  document.addEventListener('scroll', function () { tip.hidden = true; }, true);
  var order = ['', 'light', 'dark'], names = {'': 'Theme: auto', light: 'Theme: light', dark: 'Theme: dark'};
  var button = document.getElementById('theme');
  button.addEventListener('click', function () {
    var next = order[(order.indexOf(root.getAttribute('data-theme') || '') + 1) % 3];
    if (next) root.setAttribute('data-theme', next); else root.removeAttribute('data-theme');
    button.textContent = names[next];
  });
})();
"""


def build_html(run: dict) -> str:
    record = run["record"]
    rows, counts, total = guide_rows(run)
    queries = sum(len(s["rows"]) for s in run["sets"].values())
    kinds = kind_columns(run)
    situations = situation_columns(run)
    thresholds = run["thresholds"]

    def figure(svg: str, table_markdown: str = "", attributes: str = "") -> str:
        twin = (f"<details><summary>Table</summary>{md_table_to_html(table_markdown)}</details>"
                if table_markdown else "")
        return f'<figure{attributes}><div class="scroll">{svg}</div>{twin}</figure>'

    def per_view(build) -> str:
        """One figure per threshold and read-out; the filters show one."""
        return "".join(
            figure(*build(t, m), f' data-threshold="{t}" data-measure="{m}"') for t in thresholds for m in MEASURES)

    def per_threshold(build) -> str:
        return "".join(figure(*build(t), f' data-threshold="{t}"') for t in thresholds)

    def section_table(markdown: str) -> str:
        return md_table_to_html(markdown)

    guide_html = ""
    for heading, group in (("Groups of cases", "group"), ("Public data sets", "data"),
                           ("Generated data, one condition at a time", "situation")):
        selected = [row for row in rows if row["group"] == group]
        if selected:
            guide_html += f"<h3>{heading}</h3>" + section_table(table(
                ["Case", "Queries", "Best key", "Share right", "Level with the best"],
                [[row["label"] if row["group"] != "data" else f"{row['kind']}: {row['label']}", row["queries"],
                  ", ".join(code(n) for n in row["best"]), f3(row["share"]["p"]),
                  ", ".join(code(n) for n in row["level"]) or "none"] for row in selected], "lrlrl"))

    body = [f"""
<h1>KATO ranking benchmark: which <code>rank_sort_algo</code> to use</h1>
<p class="lede">How often each ranking key puts the right next event on top, measured through the REST API of a running KATO instance: {queries:,} held-out queries on {len(record['nodes'])} nodes, {len(run['keys'])} ranking keys, recall thresholds {', '.join(thresholds)}.</p>
{f'<p><strong>Note.</strong> {html.escape(record["note"])}</p>' if record.get('note') else ''}
<p>{code_html(' '.join(sentences(run, counts, total)))}</p>

<h2>Which key for which case</h2>
<p>One rule, fixed before the run. In each case the best key is the one with the highest share of queries answered right. A key is <strong>level</strong> with it when the 95% interval of the difference between the two, measured on the same queries, includes zero. Read-out: the top-ranked prediction that has a <code>future</code>. <code>recall_threshold</code> {stats.GUIDE_THRESHOLD}. This table does not follow the settings below.</p>
{guide_html}
<h3>How often each key is best or level, over the {total} single cases</h3>
{section_table(table_counts(run, counts, total))}

<form class="filters" aria-label="What the charts below show">
  <fieldset><legend>recall_threshold</legend>
    {''.join(f'<label><input type="radio" name="threshold" value="{t}"{" checked" if i == 0 else ""}><span>{t}</span></label>' for i, t in enumerate(thresholds))}
  </fieldset>
  <fieldset><legend>Read-out</legend>
    {''.join(f'<label><input type="radio" name="measure" value="{m}"{" checked" if i == 0 else ""}><span>{html.escape(MEASURES[m][0])}</span></label>' for i, m in enumerate(MEASURES))}
  </fieldset>
  <button type="button" class="theme" id="theme">Theme: auto</button>
</form>

<h2>By ranking key</h2>
{per_view(lambda t, m: (chart_headline(run, t, m, False), table_keys(run, kinds, t, m, 'Mean of the kinds')))}

<h2>By kind of data</h2>
{per_view(lambda t, m: (chart_grid(run, kinds, t, m, 'Share answered right, by kind of data and ranking key', 'Mean of the kinds', False), table_keys(run, kinds, t, m, 'Mean of the kinds')))}
"""]
    if situations:
        body.append(f"""
<h2>By situation</h2>
<p>Generated data, one condition changed at a time.</p>
{per_view(lambda t, m: (chart_grid(run, situations, t, m, 'Share answered right, by situation and ranking key', 'Mean', False), table_keys(run, situations, t, m, 'Mean')))}
""")
    if transfer_rows(run):
        body.append(f"""
<h2>Data <code>potential</code> never saw</h2>
<p>The weights of <code>potential</code> are constants fitted once. On each public data set: <code>potential</code> against the best of the other {len(run['keys']) - 1} keys on that data set, on the same queries, at <code>recall_threshold</code> {stats.GUIDE_THRESHOLD}. The other key is chosen after the fact, which favours it. The settings above do not apply here.</p>
{figure(chart_transfer(run, False))}
{section_table(table_transfer(run))}
""")
    body.append(f"""
<h2>The top prediction itself</h2>
<p>The top-ranked prediction can be a pattern that ends where the STM ends. Its <code>future</code> is empty and it names no next event.</p>
{per_threshold(lambda t: (chart_top(run, t, False), table_top(run, t)))}

<h2>Recall threshold</h2>
<p>A higher <code>recall_threshold</code> leaves fewer candidates. All three thresholds are shown; the settings above do not apply here.</p>
{figure(chart_thresholds(run, 'potential' if 'potential' in run['keys'] else run['keys'][0], False), table_thresholds(run))}
{section_table(table_threshold_cost(run))}

<h2>How sure: <code>future_potentials</code></h2>
<p>The <code>probability</code> of the top entry, against how often that entry is right.</p>
{per_threshold(lambda t: (chart_calibration(run, t, False), table_calibration(run, t)))}
""")
    if stats.endings(run, stats.GUIDE_THRESHOLD):
        body.append(f"""
<h2>When the sequence has ended: <code>ends_here</code></h2>
<p>Measured both ways: on queries where an event did follow, and on complete sequences observed to their last event.</p>
{per_threshold(lambda t: (chart_endings(run, t, False), table_endings(run, t)))}
<p>The ranking key decides how often the top prediction is a pattern that has ended. Where the sequence ended that is the right reading; where it went on, the top prediction names no event.</p>
{''.join(f'<div data-threshold="{t}">{section_table(table_no_future(run, t))}</div>' for t in thresholds)}
""")
    body.append(f"""
<h2>How sure: <code>chance_posterior</code></h2>
{''.join(f'<div data-threshold="{t}">{section_table(table_chance(run, t))}</div>' for t in thresholds)}
""")
    if stats.latency(run)["points"]:
        body.append(f"""
<h2>Request time</h2>
<p>One request at a time, <code>max_predictions</code> 100, <code>recall_threshold</code> {stats.GUIDE_THRESHOLD}, on the machine of the run. Times depend on the hardware.</p>
{figure(chart_latency(run, False), table_latency(run))}
<p>Every metric is computed for every candidate whichever key ranks them, so the key does not change the time:</p>
{section_table(table_latency_keys(run))}
""")
    body.append(f"""
<h2>The nodes and the data</h2>
{section_table(table_nodes(run))}
{section_table(table_sources(run)) if record.get('sources') else ''}
<p class="note">Generated by <code>python -m benchmarks.ranking.report</code> from the result files of one run. A share is a count of queries over a count of queries; a group figure is the mean over its query sets, each counting the same. Intervals are 95%.</p>
""")
    title = "KATO ranking benchmark"
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{title}</title>\n'
            f"<style>{charts.PAGE_STYLE}{PAGE_CSS}</style>\n</head>\n"
            f'<body><div class="viz-root"><main>{"".join(body)}</main><div id="tip" role="status" hidden></div></div>\n'
            f"<script>{PAGE_JS}</script>\n</body>\n</html>\n")


# ----------------------------------------------------------------------------

def build(run_dir: Path, out_dir: Path, log=print) -> None:
    run = stats.load_run(run_dir)
    if not run["sets"]:
        raise SystemExit(f"{run_dir} holds no completed query set")
    images = out_dir / PAGE
    images.mkdir(parents=True, exist_ok=True)
    for name, svg in build_charts(run, stats.GUIDE_THRESHOLD, True).items():
        (images / f"{name}.svg").write_text(svg)
    (out_dir / f"{PAGE}.md").write_text(build_markdown(run, PAGE))
    (images / "report.html").write_text(build_html(run))
    log(f"wrote {out_dir / (PAGE + '.md')}, the charts and {images / 'report.html'}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default=str(DEFAULT_RUN), help="the run's folder (default: %(default)s)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="where the page goes (default: %(default)s)")
    p.add_argument("--compare", nargs=2, metavar="RUN", help="compare two runs response by response, then stop")
    args = p.parse_args(argv)
    if args.compare:
        result = stats.compare(stats.load_run(Path(args.compare[0])), stats.load_run(Path(args.compare[1])))
        print(json.dumps(result, indent=1))
        return 0 if result["different"] == 0 and result["same"] > 0 else 1
    build(Path(args.run), Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
