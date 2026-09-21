"""
Recall-safe candidate bounding for the prediction path.

KATO scores a candidate pattern against the STM with ``_lcs_ratio_scorer``
(:mod:`kato.searches.pattern_search`)::

    similarity = 2 * LCS(pattern, state) / (len(pattern) + len(state))

and keeps the candidate when ``similarity >= recall_threshold``.

ClickHouse cannot evaluate that expression: it has no longest-common-subsequence
function. ``arrayLevenshteinDistance`` is a *different* metric (it permits
substitution, which LCS does not), so using it as the decision would change
predictions.

What ClickHouse *can* do is evaluate a **necessary condition** -- a quantity that
is provably never smaller than the true similarity. Two are used here, both
derived from ``M = LCS(pattern, state)``:

1. ``M <= min(P, L)``  ->  a window on the pattern's token count::

       r*L/(2-r)  <=  P  <=  L*(2-r)/r

2. ``M <= common``, where ``common`` counts pattern tokens (with multiplicity)
   that appear in the STM's symbol set::

       2 * common  >=  r * (P + L)

If either fails, ``similarity >= r`` is impossible, so the pattern can be
discarded without ever running LCS on it. Survivors go to the real scorer
unchanged, which is why predictions stay byte-identical: this removes only
candidates the scorer would have rejected anyway.

Why the arithmetic is integer and deliberately *weakened*
---------------------------------------------------------
The reference implementation is floating point, and ``float(0.1)`` is slightly
**larger** than one tenth. An exact rational comparison is therefore *stricter*
than the scorer it approximates, and rejects candidates the scorer accepts --
silent recall loss. Measured over ``r x L x P x M``, a naive ``Fraction`` bound
lost 413 candidates; the weakened integer form below lost none.

So ``recall_threshold`` is floored to ``num/DEN <= recall_threshold`` and every
comparison is done in integers. Weakening ``r`` makes both predicates strictly
more permissive, so the survivor set stays a superset of the true one.

**Rule: this bound must never be tighter than the float scorer.**
"""

import logging
import math
from dataclasses import dataclass
from fractions import Fraction
from os import environ
from typing import Any, Optional

logger = logging.getLogger('kato.filters.recall_bounds')

# Denominator for the fixed-point form of recall_threshold. 1e-6 of slack is
# far larger than the scorer's float error (~1e-16 relative) and far smaller
# than the granularity of any achievable similarity, so it costs effectively no
# selectivity while making the safety argument exact rather than empirical.
DEN = 1_000_000

# The ``length`` column is UInt32; an upper bound above this is meaningless.
UINT32_MAX = 2**32 - 1

# Guards on the STM token array. clickhouse-connect interpolates parameters into
# the statement text client-side (``query % {...}``), so the array is billed
# against ClickHouse's max_query_size (262144 bytes by default) -- and it appears
# twice in the statement. 32768 bytes of tokens costs ~64KB of the budget.
MAX_STATE_TOKEN_BYTES = int(environ.get('KATO_RECALL_BOUND_MAX_TOKEN_BYTES', '32768'))

# Secondary guard: ``has(<constant array>, t)`` inside a lambda is evaluated per
# pattern token, so a very large constant array makes the surviving-row scan
# O(P * len(tokens)).
MAX_STATE_TOKENS = int(environ.get('KATO_RECALL_BOUND_MAX_TOKENS', '4096'))

# Query used when no bound applies -- byte-identical to the pre-bound behaviour.
_UNBOUNDED_QUERY = """
            SELECT name, pattern_data, length
            FROM patterns_data
            WHERE kb_id = %(kb_id)s
        """

_BOUNDED_QUERY_LENGTH_ONLY = """
            SELECT name, pattern_data, length
            FROM patterns_data
            WHERE kb_id = %(kb_id)s
              AND length BETWEEN %(min_length)s AND %(max_length)s
        """

# ``hasAny`` is logically implied by the arrayCount clause, but it is the clause
# the idx_token_bloom skip index can prune granules with -- that is where the
# reduction actually comes from. Keep both.
_BOUNDED_QUERY_FULL = """
            SELECT name, pattern_data, length
            FROM patterns_data
            WHERE kb_id = %(kb_id)s
              AND length BETWEEN %(min_length)s AND %(max_length)s
              AND hasAny(token_set, %(state_tokens)s)
              AND 2 * toInt64(arrayCount(t -> has(%(state_tokens)s, t), arrayFlatten(pattern_data))) * %(den)s
                  >= %(num)s * toInt64(length + %(stm_len)s)
        """


@dataclass(frozen=True)
class RecallBound:
    """A recall-safe bound on which patterns can clear ``recall_threshold``.

    ``applied=False`` means no bound could be established and the caller must
    query the full corpus. Never treat an unapplied bound as "nothing matches".
    """

    applied: bool
    reason: str
    use_token_overlap: bool = False
    min_length: int = 0
    max_length: int = UINT32_MAX
    num: int = 0
    den: int = DEN
    state_tokens: tuple = ()
    stm_len: int = 0


def _ceil_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division. No floats, so no rounding surprises."""
    return -((-numerator) // denominator)


def weakened_threshold(recall_threshold: float) -> int:
    """Floor ``recall_threshold`` onto the ``num/DEN`` grid.

    The result satisfies ``num/DEN <= recall_threshold`` exactly, which is what
    makes the derived predicates permissive rather than strict.
    """
    return math.floor(Fraction(recall_threshold) * DEN)


def similarity_upper_bound(pattern_tokens, state_token_set, stm_len: int) -> Fraction:
    """Upper bound on ``2*LCS/(P+L)`` using only symbol membership.

    The Python twin of the SQL ``arrayCount`` clause. Used by the audit mode and
    by tests that pin the SQL expression to this one.
    """
    total = len(pattern_tokens) + stm_len
    if total == 0:
        return Fraction(0)
    common = sum(1 for token in pattern_tokens if token in state_token_set)
    return Fraction(2 * common, total)


def compute_recall_bound(
    state: list,
    recall_threshold: Optional[float],
    use_token_matching: bool,
    enabled: bool = True,
) -> RecallBound:
    """Derive the strongest recall-safe bound available for this request.

    Degrades through a ladder of rungs, each a superset of the one below it, so
    every rung is recall-safe. When nothing can be established the bound is
    ``applied=False`` and the caller falls back to the full corpus.

    Args:
        state: Flattened STM token list -- the ``L`` sequence in the scorer.
        recall_threshold: The *resolved* threshold, i.e. the same value the
            scorer will use. Never pass a raw ``SessionConfiguration`` field:
            those default to ``None``, and a bound computed from a different
            threshold than the scorer uses is silent recall loss.
        use_token_matching: The *resolved* matching mode. Must be the value the
            scorer will use, for the same reason.
        enabled: Kill switch.
    """
    if not enabled:
        return RecallBound(applied=False, reason='kill_switch')

    # Character-level mode scores fuzz.ratio(' '.join(pattern), ' '.join(state)),
    # a CHARACTER metric. Two strings can share many characters and no tokens, so
    # neither a token-count window nor token overlap bounds it. No bound is valid.
    if not use_token_matching:
        return RecallBound(applied=False, reason='character_mode')

    # Belt-and-braces with the config-boundary rejection of recall_threshold <= 0.
    # Never assume the validator ran: at r=0 every pattern qualifies (sim >= 0
    # always), so any filter at all would be lossy.
    if recall_threshold is None:
        return RecallBound(applied=False, reason='threshold_none')

    num = weakened_threshold(recall_threshold)
    if num <= 0:
        return RecallBound(applied=False, reason='threshold_not_positive')

    stm_len = len(state)
    if stm_len == 0:
        return RecallBound(applied=False, reason='empty_state')

    # Length window, from M <= min(P, L). Integer arithmetic throughout.
    #   P >= r*L/(2-r)   and   P <= L*(2-r)/r
    # with r replaced by num/DEN.
    min_length = _ceil_div(num * stm_len, 2 * DEN - num)
    max_length = min((stm_len * (2 * DEN - num)) // num, UINT32_MAX)

    # Deduplicate: patterns repeat symbols, and only membership matters.
    # Sorted so the query text is reproducible across processes -- set iteration
    # order varies with PYTHONHASHSEED, and irreproducible SQL makes EXPLAIN
    # comparison and log diffing useless.
    state_tokens = tuple(sorted(set(state)))

    # Serialized cost: quotes + comma per token, and the array appears twice.
    token_bytes = sum(len(token) + 3 for token in state_tokens)
    if len(state_tokens) > MAX_STATE_TOKENS or token_bytes > MAX_STATE_TOKEN_BYTES:
        # Drop to the length window alone rather than truncating the token list.
        # A partial list under-counts ``common`` and would make the overlap
        # predicate reject genuine matches.
        logger.info(
            "Recall bound: token overlap skipped (%d tokens, %d bytes); using length window only",
            len(state_tokens), token_bytes
        )
        return RecallBound(
            applied=True,
            reason='token_payload_too_large',
            use_token_overlap=False,
            min_length=min_length,
            max_length=max_length,
            num=num,
            stm_len=stm_len,
        )

    return RecallBound(
        applied=True,
        reason='ok',
        use_token_overlap=True,
        min_length=min_length,
        max_length=max_length,
        num=num,
        state_tokens=state_tokens,
        stm_len=stm_len,
    )


def build_pattern_query(bound: RecallBound) -> tuple[str, dict[str, Any]]:
    """Render ``bound`` as a ClickHouse statement plus its parameters.

    ``kb_id`` is deliberately absent from the returned parameters: the executor
    owns it and treats it as a reserved name.
    """
    if not bound.applied:
        return _UNBOUNDED_QUERY, {}

    params: dict[str, Any] = {
        'min_length': bound.min_length,
        'max_length': bound.max_length,
    }

    if not bound.use_token_overlap:
        return _BOUNDED_QUERY_LENGTH_ONLY, params

    # A list (not a tuple) so clickhouse-connect renders ClickHouse array
    # syntax ['a','b'], which is what has()/hasAny() require.
    params['state_tokens'] = list(bound.state_tokens)
    params['num'] = bound.num
    params['den'] = bound.den
    params['stm_len'] = bound.stm_len
    return _BOUNDED_QUERY_FULL, params
