"""Diagnostics for a prediction that returned nothing.

A bare `assert len(predictions) > 0` says only that the answer was empty. It
cannot distinguish a pattern that was never written, from one written but not yet
queryable, from one present in both stores that the candidate pipeline declined
to select. Those have different causes and different fixes, and on an
intermittent CI failure there is no second chance to look.

`describe_prediction_miss` gathers that state so a failure names its own cause.
Attach it to the assertion message of any test whose emptiness would be
surprising.
"""

from typing import Any, Optional


def _clickhouse(query: str) -> str:
    import requests
    try:
        r = requests.post('http://localhost:8123/', data=query.encode(), timeout=5)
        return r.text.strip() if r.status_code == 200 else f"<http {r.status_code}: {r.text.strip()[:200]}>"
    except Exception as e:  # noqa: BLE001 - diagnostics must never raise
        return f"<unreachable: {type(e).__name__}: {e}>"


def describe_prediction_miss(kato_fixture, expected_symbols: Optional[list[str]] = None) -> str:
    """Return a multi-line description of the stores behind an empty prediction.

    Never raises: a diagnostic that fails takes the real failure's message with
    it. Every field degrades to an explanatory placeholder instead.
    """
    lines: list[str] = []
    add = lines.append

    try:
        node_id = kato_fixture.processor_id
        kb_id = kato_fixture._get_actual_kb_id(node_id)
    except Exception as e:  # noqa: BLE001
        return f"  <diagnostics unavailable: could not resolve kb_id: {type(e).__name__}: {e}>"

    add(f"  node_id={node_id}")
    add(f"  kb_id={kb_id}")

    # Is anything in patterns_data at all, and is it queryable right now?
    add(f"  patterns_data rows for this kb_id: {_clickhouse(f'SELECT count() FROM kato.patterns_data WHERE kb_id = {kb_id!r}')}")
    add(f"  patterns_metadata rows for this kb_id: {_clickhouse(f'SELECT count() FROM kato.patterns_metadata WHERE kb_id = {kb_id!r}')}")
    # first_token is included because _predict_single_symbol_fast filters on it
    # rather than on pattern_data, so a row that looks present can still be
    # unreachable by that path if the column disagrees with pattern_data[0][0].
    names = _clickhouse(
        f"SELECT name, first_token, length, toString(pattern_data) FROM kato.patterns_data "
        f"WHERE kb_id = {kb_id!r} ORDER BY name LIMIT 10 FORMAT TSV"
    )
    add("  patterns_data (name, first_token, length, pattern_data):\n    " + (names.replace('\n', '\n    ') if names else '<none>'))

    # Rows still sitting in the server's async_insert buffer would explain a
    # write that happened but is not yet visible to a SELECT.
    # system.asynchronous_insert_log is itself buffered and flushes on its own
    # schedule, so an empty result here means "not yet recorded", never "no async
    # inserts happened". Read it over a wide window and treat it as corroboration
    # rather than as proof either way. A non-zero lag_ms on a recent row is the
    # signal worth having: it means a write really was waiting to become
    # queryable.
    add("  recent patterns_data async inserts "
        "(status, applied timeout ms, flush lag ms) -- this log flushes lazily, "
        "so empty is inconclusive:\n    " + _clickhouse(
            "SELECT status, timeout_milliseconds, "
            "round((flush_time_microseconds - event_time_microseconds)/1000.0, 3) AS lag_ms "
            "FROM system.asynchronous_insert_log "
            "WHERE table = 'patterns_data' AND event_time > now() - INTERVAL 15 MINUTE "
            "ORDER BY event_time DESC LIMIT 5 FORMAT TSV"
        ).replace('\n', '\n    '))

    # Replay the exact predicate _predict_single_symbol_fast uses. If this
    # returns rows but the prediction was empty, the miss is downstream of
    # candidate selection; if it returns nothing while pattern_data plainly
    # contains the symbol, first_token is the culprit.
    if expected_symbols:
        sym = expected_symbols[0]
        add(f"  fast-path predicate (first_token = {sym!r}): " + _clickhouse(
            f"SELECT count() FROM kato.patterns_data "
            f"WHERE kb_id = {kb_id!r} AND first_token = {sym!r}"
        ))
        add(f"  same, via pattern_data[1][1] = {sym!r}: " + _clickhouse(
            f"SELECT count() FROM kato.patterns_data "
            f"WHERE kb_id = {kb_id!r} AND pattern_data[1][1] = {sym!r}"
        ))

    # Redis side: frequency keys are the authority on which patterns exist.
    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        freq_keys = list(client.scan_iter(match=f"{kb_id}:frequency:*", count=500))
        add(f"  redis frequency keys: {len(freq_keys)}")
        if freq_keys:
            add(f"    e.g. {sorted(freq_keys)[:5]}")
        add(f"  redis stats:version: {client.get(f'{kb_id}:stats:version')}")
        add(f"  redis total_unique_patterns: {client.get(f'{kb_id}:global:total_unique_patterns')}")
        if expected_symbols:
            for sym in expected_symbols[:5]:
                members = client.smembers(f"{kb_id}:symbol_to_patterns:{sym}")
                add(f"  redis symbol_to_patterns[{sym!r}]: {sorted(members) if members else '<empty>'}")
    except Exception as e:  # noqa: BLE001
        add(f"  <redis unavailable: {type(e).__name__}: {e}>")

    # Configuration that decides whether a present pattern is selected at all.
    try:
        cfg: dict[str, Any] = kato_fixture.session_config or {}
        interesting = {
            k: cfg[k] for k in
            ('recall_threshold', 'use_token_matching', 'filter_pipeline',
             'max_predictions', 'sort_symbols', 'fuzzy_token_threshold')
            if k in cfg
        }
        add(f"  session config overrides: {interesting or '<none set; system defaults apply>'}")
    except Exception as e:  # noqa: BLE001
        add(f"  <session config unavailable: {type(e).__name__}: {e}>")

    try:
        add(f"  stm at time of failure: {kato_fixture.get_stm()}")
    except Exception as e:  # noqa: BLE001
        add(f"  <stm unavailable: {type(e).__name__}: {e}>")

    return "\n".join(lines)
