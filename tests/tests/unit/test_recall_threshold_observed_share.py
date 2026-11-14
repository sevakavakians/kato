"""
Pins the recall_threshold table in docs/users/configuration.md to the code.

For an STM whose every symbol matches, the table gives three numbers per
threshold: the share of a pattern that must be observed before the pattern is
returned, the STM length that takes for a 100-symbol pattern, and the longest
pattern a 10-symbol STM can return. All three follow from

    similarity = 2 * LCS / (len(pattern) + len(STM))  >=  recall_threshold

The tests recompute them with the scorer the search uses and with the candidate
bound that runs before it. If the similarity formula or the comparison changes,
they fail, and the table has to change with them.

These tests need no database and no services.
"""

import pytest

from kato.filters.recall_bounds import compute_recall_bound
from kato.searches.pattern_search import _lcs_ratio_scorer

# The table, row for row:
# recall_threshold, share of the pattern that must be observed (percent),
# STM symbols needed for a 100-symbol pattern, longest pattern a 10-symbol STM returns.
DOCUMENTED_TABLE = [
    (0.02, 1.0, 2, 990),
    (0.1, 5.3, 6, 190),
    (0.2, 11.1, 12, 90),
    (0.3, 17.6, 18, 56),
    (0.4, 25.0, 25, 40),
    (0.5, 33.3, 34, 30),
    (0.6, 42.9, 43, 23),
    (0.7, 53.8, 54, 18),
    (0.8, 66.7, 67, 15),
    (0.9, 81.8, 82, 12),
    (1.0, 100.0, 100, 10),
]

# "set recall_threshold no higher than 2f / (1 + f)":
# share observed (percent), the threshold the guide names for it.
DOCUMENTED_CHOICES = [(10, 0.18), (25, 0.40), (50, 0.66), (75, 0.85)]

MIN_STM = 2  # a one-symbol STM is a lookup and never reaches the scorer


def symbols(count: int) -> list:
    return [f"s{i:04d}" for i in range(count)]


def returned(pattern: list, stm: list, recall_threshold: float) -> bool:
    """Whether the search returns ``pattern`` for ``stm``.

    The candidate bound first, with its predicates applied as the SQL applies
    them, then the scorer with the caller's float round trip.
    """
    bound = compute_recall_bound(stm, recall_threshold, use_token_matching=True)
    if bound.applied:
        if not (bound.min_length <= len(pattern) <= bound.max_length):
            return False
        if bound.use_token_overlap:
            observed = set(stm)
            common = sum(1 for token in pattern if token in observed)
            if 2 * common * bound.den < bound.num * (len(pattern) + bound.stm_len):
                return False
    similarity = _lcs_ratio_scorer(stm, pattern) / 100.0
    return similarity >= recall_threshold


@pytest.mark.parametrize("recall_threshold, share, stm_needed, longest", DOCUMENTED_TABLE)
def test_share_of_the_pattern_that_must_be_observed(recall_threshold, share, stm_needed, longest):
    assert round(100 * recall_threshold / (2 - recall_threshold), 1) == share


@pytest.mark.parametrize("recall_threshold, share, stm_needed, longest", DOCUMENTED_TABLE)
def test_stm_symbols_needed_for_a_100_symbol_pattern(recall_threshold, share, stm_needed, longest):
    pattern = symbols(100)
    first = next(length for length in range(MIN_STM, 101) if returned(pattern, pattern[:length], recall_threshold))
    assert first == stm_needed
    # once returned, a longer observed prefix keeps it returned
    assert all(returned(pattern, pattern[:length], recall_threshold) for length in range(first, 101))


@pytest.mark.parametrize("recall_threshold, share, stm_needed, longest", DOCUMENTED_TABLE)
def test_longest_pattern_a_10_symbol_stm_can_return(recall_threshold, share, stm_needed, longest):
    at_limit, past_limit = symbols(longest), symbols(longest + 1)
    assert returned(at_limit, at_limit[:10], recall_threshold)
    assert not returned(past_limit, past_limit[:10], recall_threshold)


@pytest.mark.parametrize("share, recall_threshold", DOCUMENTED_CHOICES)
def test_threshold_to_choose_for_a_share_observed(share, recall_threshold):
    pattern = symbols(100)
    observed = pattern[:share]
    assert recall_threshold <= 2 * (share / 100) / (1 + share / 100)
    assert returned(pattern, observed, recall_threshold)
    assert not returned(pattern, observed, round(recall_threshold + 0.01, 2))


def test_an_unmatched_stm_symbol_raises_the_share_needed():
    pattern = symbols(100)
    assert returned(pattern, pattern[:25], 0.4)
    assert not returned(pattern, pattern[:25] + ["not-in-the-pattern"], 0.4)


def test_symbols_are_counted_not_events():
    # Four events of three symbols; the STM is the first event. KATO matches on
    # the flattened symbols, so 3 of 12 symbols is the 25% that 0.4 requires.
    events = [["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"], ["j", "k", "l"]]
    pattern = [symbol for event in events for symbol in event]
    assert returned(pattern, events[0], 0.4)
    assert not returned(pattern, events[0][:2], 0.4)


def test_position_of_the_observed_symbols_does_not_matter():
    pattern = symbols(100)
    for start in (0, 40, 75):
        assert returned(pattern, pattern[start : start + 25], 0.4)
        assert not returned(pattern, pattern[start : start + 24], 0.4)
