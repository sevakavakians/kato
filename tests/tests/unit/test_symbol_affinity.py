"""
Symbol affinity tests for KATO.

These tests validate:
1. Per-symbol affinity accumulation from averaged emotives at learn time
2. Affinity summing across multiple pattern learns
3. Multi-key emotive handling
4. No affinity when no emotives provided
5. Affinity accumulation on pattern re-learning
"""
import json

import pytest
import redis


def _get_symbol_affinity(kato_fixture, symbol: str) -> dict:
    """Get affinity directly from Redis for a symbol."""
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    kb_id = kato_fixture._get_actual_kb_id(kato_fixture.processor_id)
    affinity_key = f"{kb_id}:affinity:{symbol}"
    raw = r.hgetall(affinity_key)
    return {k: float(v) for k, v in raw.items()} if raw else {}


def test_affinity_single_pattern_learn(kato_fixture):
    """Learning one pattern with emotives gives each symbol the averaged emotive values as affinity."""
    kato_fixture.clear_all_memory()

    # Observe with emotives across 2 observations, then learn
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 0.8}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 0.4}})
    kato_fixture.learn()

    # Averaged emotive: joy = (0.8 + 0.4) / 2 = 0.6
    for symbol in ['A', 'B']:
        affinity = _get_symbol_affinity(kato_fixture, symbol)
        assert 'joy' in affinity, f"Symbol {symbol} should have 'joy' affinity"
        assert abs(affinity['joy'] - 0.6) < 0.01, \
            f"Symbol {symbol} affinity joy should be ~0.6, got {affinity['joy']}"


def test_affinity_accumulates_across_patterns(kato_fixture):
    """Affinity sums across multiple pattern learns for shared symbols."""
    kato_fixture.clear_all_memory()

    # Learn pattern 1: [A, B] with joy=1.0
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 1.0}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 1.0}})
    kato_fixture.learn()

    # Start a new session so the emotives_accumulator resets for pattern 2
    kato_fixture.session_id = None

    # Learn pattern 2: [B, C] with joy=2.0
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 2.0}})
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'joy': 2.0}})
    kato_fixture.learn()

    # A only in pattern 1: joy = 1.0
    a_affinity = _get_symbol_affinity(kato_fixture, 'A')
    assert abs(a_affinity['joy'] - 1.0) < 0.01, f"A should have joy=1.0, got {a_affinity}"

    # B in both patterns: joy = 1.0 + 2.0 = 3.0
    b_affinity = _get_symbol_affinity(kato_fixture, 'B')
    assert abs(b_affinity['joy'] - 3.0) < 0.01, f"B should have joy=3.0, got {b_affinity}"

    # C only in pattern 2: joy = 2.0
    c_affinity = _get_symbol_affinity(kato_fixture, 'C')
    assert abs(c_affinity['joy'] - 2.0) < 0.01, f"C should have joy=2.0, got {c_affinity}"


def test_affinity_multi_key_emotives(kato_fixture):
    """Affinity handles multiple emotive keys correctly."""
    kato_fixture.clear_all_memory()

    kato_fixture.observe({'strings': ['X'], 'vectors': [], 'emotives': {'joy': 0.8, 'fear': 0.2}})
    kato_fixture.observe({'strings': ['Y'], 'vectors': [], 'emotives': {'joy': 0.4, 'fear': 0.6}})
    kato_fixture.learn()

    # Averaged: joy = (0.8+0.4)/2 = 0.6, fear = (0.2+0.6)/2 = 0.4
    for symbol in ['X', 'Y']:
        affinity = _get_symbol_affinity(kato_fixture, symbol)
        assert abs(affinity['joy'] - 0.6) < 0.01, f"{symbol} joy should be ~0.6"
        assert abs(affinity['fear'] - 0.4) < 0.01, f"{symbol} fear should be ~0.4"


def test_affinity_no_emotives(kato_fixture):
    """No affinity keys created when learning without emotives."""
    kato_fixture.clear_all_memory()

    kato_fixture.observe({'strings': ['P'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['Q'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    for symbol in ['P', 'Q']:
        affinity = _get_symbol_affinity(kato_fixture, symbol)
        assert affinity == {}, f"Symbol {symbol} should have no affinity, got {affinity}"


def test_affinity_relearn_accumulates(kato_fixture):
    """Re-learning the same pattern accumulates affinity (not idempotent)."""
    kato_fixture.clear_all_memory()

    # Learn pattern [A, B] with joy=1.0
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 1.0}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 1.0}})
    kato_fixture.learn()

    # Start new session to reset emotives_accumulator
    kato_fixture.session_id = None

    # Re-learn same pattern [A, B] with joy=2.0
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 2.0}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 2.0}})
    kato_fixture.learn()

    # Affinity should be sum of both learns: 1.0 + 2.0 = 3.0
    for symbol in ['A', 'B']:
        affinity = _get_symbol_affinity(kato_fixture, symbol)
        assert abs(affinity['joy'] - 3.0) < 0.01, \
            f"Symbol {symbol} affinity should be 3.0 after re-learn, got {affinity}"


def test_affinity_varying_emotive_keys_across_learns(kato_fixture):
    """Affinity accumulates new emotive keys introduced in later learns."""
    kato_fixture.clear_all_memory()

    # Learn pattern [D, E] with utility=30, energy=-5
    kato_fixture.observe({'strings': ['D'], 'vectors': [], 'emotives': {'utility': 30, 'energy': -5}})
    kato_fixture.observe({'strings': ['E'], 'vectors': [], 'emotives': {'utility': 30, 'energy': -5}})
    kato_fixture.learn()

    # Start new session to reset emotives_accumulator
    kato_fixture.session_id = None

    # Learn pattern [D, F] with utility=-5, happy=12
    kato_fixture.observe({'strings': ['D'], 'vectors': [], 'emotives': {'utility': -5, 'happy': 12}})
    kato_fixture.observe({'strings': ['F'], 'vectors': [], 'emotives': {'utility': -5, 'happy': 12}})
    kato_fixture.learn()

    # D in both: utility = 30 + (-5) = 25, energy = -5, happy = 12
    d_affinity = _get_symbol_affinity(kato_fixture, 'D')
    assert abs(d_affinity['utility'] - 25.0) < 0.01, f"D utility should be 25, got {d_affinity}"
    assert abs(d_affinity['energy'] - (-5.0)) < 0.01, f"D energy should be -5, got {d_affinity}"
    assert abs(d_affinity['happy'] - 12.0) < 0.01, f"D happy should be 12, got {d_affinity}"

    # E only in first: utility=30, energy=-5
    e_affinity = _get_symbol_affinity(kato_fixture, 'E')
    assert abs(e_affinity['utility'] - 30.0) < 0.01, f"E utility should be 30, got {e_affinity}"
    assert abs(e_affinity['energy'] - (-5.0)) < 0.01, f"E energy should be -5, got {e_affinity}"
    assert 'happy' not in e_affinity, f"E should not have 'happy', got {e_affinity}"

    # F only in second: utility=-5, happy=12
    f_affinity = _get_symbol_affinity(kato_fixture, 'F')
    assert abs(f_affinity['utility'] - (-5.0)) < 0.01, f"F utility should be -5, got {f_affinity}"
    assert abs(f_affinity['happy'] - 12.0) < 0.01, f"F happy should be 12, got {f_affinity}"
    assert 'energy' not in f_affinity, f"F should not have 'energy', got {f_affinity}"
