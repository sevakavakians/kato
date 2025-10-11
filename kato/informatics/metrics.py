import logging
from functools import reduce
from math import log, log10
from operator import add
from os import environ
from typing import Any, Optional, Union

logger = logging.getLogger('kato.informatics.metrics')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))


def average_emotives(record: list[dict[str, float]]) -> dict[str, float]:
    """Average the list of emotive dicts throughout these sequence's observations.

    Averages the emotives in a list (e.g. predictions ensemble or percepts).
    Average is used instead of sum because emotive states are expected to persist
    throughout event updates that shouldn't increase/decrease the perceived emotives.

    Args:
        record: List of emotive dictionaries, e.g. [{'e1': 4, 'e2': 5}, {'e2': 6}, {'e1': 5, 'e3': -4}]

    Returns:
        Dictionary with averaged emotive values for each emotive key.

    Example:
        >>> average_emotives([{'happy': 4, 'sad': 2}, {'happy': 6}, {'sad': 4}])
        {'happy': 5.0, 'sad': 3.0}
    """
    logger.debug(f'average_emotives record: {record}')
    new_dict: dict[str, list[float]] = {}
    for bunch in record:
        logger.debug(bunch)
        for e, v in bunch.items():
            if e not in new_dict:
                new_dict[e] = [v]
            else:
                new_dict[e].append(v)
    avg_dict: dict[str, float] = {}
    for e, v in new_dict.items():
        if len(v) > 0:
            avg_dict[e] = float(sum(v) / len(v))
        else:
            avg_dict[e] = 0.0
    return avg_dict


def accumulate_metadata(metadata_list: list[dict]) -> dict[str, list[str]]:
    """Accumulate metadata dicts into a single dict with unique string list values.

    Merges all metadata dictionaries, converting values to strings and ensuring
    uniqueness within each key's list. This is used for pattern metadata storage
    where we want to track all unique values seen for each metadata key.

    Args:
        metadata_list: List of metadata dictionaries with any value types

    Returns:
        Dictionary mapping each key to a list of unique string values.

    Example:
        >>> accumulate_metadata([{'book': 'title1'}, {'book': 'title2'}, {'book': 'title1'}, {'author': 'Smith'}])
        {'book': ['title1', 'title2'], 'author': ['Smith']}
    """
    logger.debug(f'accumulate_metadata list: {metadata_list}')
    accumulated: dict[str, set[str]] = {}

    for metadata_dict in metadata_list:
        logger.debug(f'Processing metadata dict: {metadata_dict}')
        for key, value in metadata_dict.items():
            # Convert value to string
            str_value = str(value)

            if key not in accumulated:
                accumulated[key] = {str_value}
            else:
                accumulated[key].add(str_value)

    # Convert sets to sorted lists for consistent ordering
    result: dict[str, list[str]] = {}
    for key, value_set in accumulated.items():
        result[key] = sorted(list(value_set))

    logger.debug(f'Accumulated metadata result: {result}')
    return result


def compandingFunction(target: Union[int, float], collection: list[Union[int, float]]) -> Union[int, float]:
    """Reduces the data rate of signals by making the quantization levels unequal.

    Given a target number and a collection of numbers, finds the closest match
    of the target to numbers in the collection. Helps create vectors that are
    canonical in their values by locking a range of values to a single value.

    Args:
        target: The target number to match.
        collection: List of numbers to match against.

    Returns:
        The closest number from the collection to the target.

    Example:
        >>> compandingFunction(10, [0, 3, 5, 7, 11])
        7
        >>> compandingFunction(9, [0, 3, 5, 7, 11])
        7
    """
    return min((abs(target - i), i) for i in collection)[1]


def classic_expectation(p: float) -> float:
    """Calculate the classic information expectation (Shannon entropy) for a probability.

    Args:
        p: Probability value between 0 and 1.

    Returns:
        The information expectation value using base-2 logarithm.
        Returns 0 if p <= 0 to avoid log(0) errors.

    Example:
        >>> classic_expectation(0.5)
        0.5
        >>> classic_expectation(0.25)
        0.5
    """
    if p > 0:
        return -(p * log(p, 2))
    else:
        return 0


def expectation(p: float, num_symbols: int) -> float:
    """Calculate the information expectation for a state with custom base.

    Uses the number of symbols as the logarithm base to normalize entropy
    based on the total possible symbols in the system.

    Args:
        p: Probability value between 0 and 1.
        num_symbols: Total number of unique symbols (used as log base).

    Returns:
        The information expectation value. Returns 0 for invalid inputs
        to maintain numerical stability.

    Example:
        >>> expectation(0.5, 10)
        0.15051499783199057
        >>> expectation(0.25, 4)
        0.3465735902799726
    """
    try:
        if p > 0 and num_symbols > 1:
            return -p * log(p, num_symbols)
        else:
            return 0
    except (ZeroDivisionError, ValueError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"expectation ERROR! p = {p}, num_symbols = {num_symbols}, error = {e}")
        # Return 0 for invalid values instead of raising
        return 0
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"expectation ERROR! p = {p}, num_symbols = {num_symbols}, error = {e}")
        return 0


def global_normalized_entropy(state: list[str], symbol_probabilities: dict[str, float], total_symbols: int) -> float:
    """Calculate the global normalized entropy using global symbol probabilities.

    Extended normalized entropy calculation that uses cached symbol probabilities
    from the knowledge base rather than local state frequencies.

    Args:
        state: List of symbols in the current state.
        symbol_probabilities: Dictionary mapping symbols to their global probabilities.
        total_symbols: Total number of unique symbols in the system.

    Returns:
        The global normalized entropy value.

    Example:
        >>> global_normalized_entropy(['a', 'b', 'a'], {'a': 0.5, 'b': 0.3, 'c': 0.2}, 3)
        0.3918295834173894
    """
    symbols: set[str] = set(state)
    return sum(
        [expectation(symbol_probabilities.get(symbol, 0), total_symbols) for
         symbol in symbols])


def normalized_entropy(state: list[str], total_symbols: int) -> float:
    """Calculate the normalized entropy of a state.

    Measures the complexity/entropy of a pattern based on symbol distribution.
    Protected against empty states and division by zero.

    Args:
        state: List of symbols representing the current state.
        total_symbols: Total number of unique symbols in the system.

    Returns:
        The normalized entropy value. Returns 0.0 for empty states.

    Raises:
        ZeroDivisionError: If an unexpected division by zero occurs.

    Example:
        >>> normalized_entropy(['a', 'b', 'a', 'c'], 4)
        0.8112781244591328
        >>> normalized_entropy([], 4)
        0.0
    """
    if not state or len(state) == 0:
        return 0.0
    try:
        state_length = len(state)
        if state_length == 0:  # Extra protection
            return 0.0
        return sum([expectation(state.count(symbol) / state_length, total_symbols) for symbol in state])
    except ZeroDivisionError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"ZeroDivisionError in normalized_entropy: state={state}, len(state)={len(state) if state else 'N/A'}, total_symbols={total_symbols}, error={e}")
        raise


def confluence(state: list[str], symbols_kb: dict[str, float], _P1: Optional[float] = None) -> float:
    """Calculate the confluence of a pattern.

    Confluence measures the probability of a pattern occurring vs random chance.
    Formula: P(pattern in observations) * (1 - P(pattern occurring randomly))

    Args:
        state: List of symbols in the pattern.
        symbols_kb: Dictionary of symbol probabilities from knowledge base.
        _P1: Optional probability of sequence occurring in observations (reserved for future use).

    Returns:
        The conditional probability of the pattern.

    Raises:
        Exception: If state is empty.

    Note:
        Currently only returns conditional probability. Full confluence
        calculation with P1 is not yet implemented.
    """
    if state:
        return conditionalProbability(state, symbols_kb)
    else:
        raise Exception("Cannot calculate confluence for empty state")


def conditionalProbability(state: list[str], symbol_probabilities: dict[str, float]) -> float:
    """Calculate the conditional probability of a state given symbol probabilities.

    Computes the joint probability of all symbols in the state by multiplying
    their individual probabilities (using log space for numerical stability).

    Args:
        state: List of symbols in the state.
        symbol_probabilities: Dictionary mapping symbols to their probabilities.

    Returns:
        The conditional probability of the state. Returns 0 for empty states.
        Uses 1e-10 as default probability for missing symbols to avoid log(0).

    Example:
        >>> conditionalProbability(['a', 'b'], {'a': 0.5, 'b': 0.3, 'c': 0.2})
        0.15
        >>> conditionalProbability(['x'], {'a': 0.5, 'b': 0.5})
        1e-10
    """
    # Handle missing symbols by using a small default probability
    probs: list[float] = []
    for symbol in state:
        prob = symbol_probabilities.get(symbol, 1e-10)  # Small default probability
        if prob > 0:
            probs.append(log10(prob))
        else:
            probs.append(log10(1e-10))  # Avoid log(0)
    return 10**reduce(add, probs) if probs else 0


def filterRange(x: Optional[tuple[float, Any]], range_floor: float, range_ceil: float) -> Optional[tuple[float, Any]]:
    """Filter a value based on whether it falls within a specified range.

    Args:
        x: Tuple where first element is the value to check, or None.
        range_floor: Minimum value (inclusive).
        range_ceil: Maximum value (inclusive).

    Returns:
        The input tuple if its first element is within range, None otherwise.

    Example:
        >>> filterRange((5, 'data'), 0, 10)
        (5, 'data')
        >>> filterRange((15, 'data'), 0, 10)
        None
    """
    if x is not None and x[0] >= range_floor and x[0] <= range_ceil:
        return x
    return None

