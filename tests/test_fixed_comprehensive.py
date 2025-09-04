"""Fixed comprehensive pattern test."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))
from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings

def test_long_sequence_basic_fixed(kato_fixture):
    """Test learning and predicting a long sequence of events - FIXED."""
    kato_fixture.clear_all_memory()
    
    # Ensure recall_threshold is set to default
    kato_fixture.set_recall_threshold(0.1)
    
    # Create a sequence with 12 events, totaling 36 strings
    sequence = [
        ['alpha', 'beta', 'gamma'],
        ['delta', 'epsilon'],
        ['zeta', 'eta', 'theta'],
        ['iota', 'kappa'],
        ['lambda', 'mu', 'nu'],
        ['xi', 'omicron'],
        ['pi', 'rho', 'sigma'],
        ['tau', 'upsilon'],
        ['phi', 'chi', 'psi'],
        ['omega', 'one'],
        ['two', 'three', 'four'],
        ['five', 'six']
    ]
    
    # Learn the sequence
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|')
    
    # Test prediction at beginning (observe first 2 events for 2+ strings)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['alpha', 'beta', 'gamma']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['delta', 'epsilon']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Debug output
    print(f"\nGot {len(predictions)} predictions")
    if predictions:
        print(f"First prediction: {predictions[0].get('name')}")
        print(f"Matches: {predictions[0].get('matches', [])}")
    
    assert len(predictions) > 0
    # Should predict future events
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            future = pred.get('future', [])
            assert len(future) > 0, "Should have future events"
            break

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-xvs"])