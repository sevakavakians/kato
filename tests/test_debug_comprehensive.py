"""Debug test for comprehensive patterns."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))
from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings

def test_debug(kato_fixture):
    """Debug comprehensive pattern test."""
    print("\n=== Starting debug test ===")
    
    # Clear and setup
    result = kato_fixture.clear_all_memory()
    print(f"Clear result: {result}")
    
    # Small test sequence
    sequence = [
        ['alpha', 'beta', 'gamma'],
        ['delta', 'epsilon'],
        ['zeta', 'eta', 'theta'],
    ]
    
    # Learn the sequence
    print("\n1. Learning sequence...")
    for event in sequence:
        sorted_event = sort_event_strings(event)
        print(f"  Observing: {sorted_event}")
        result = kato_fixture.observe({'strings': sorted_event, 'vectors': [], 'emotives': {}})
        print(f"  Result: {result}")
    
    pattern_name = kato_fixture.learn()
    print(f"Learned pattern: {pattern_name}")
    
    # Check STM after learning
    stm = kato_fixture.get_short_term_memory()
    print(f"STM after learning: {stm}")
    
    # Clear STM and observe first 2 events
    print("\n2. Testing prediction...")
    kato_fixture.clear_short_term_memory()
    
    event1 = sort_event_strings(['alpha', 'beta', 'gamma'])
    print(f"  Observing: {event1}")
    kato_fixture.observe({'strings': event1, 'vectors': [], 'emotives': {}})
    
    event2 = sort_event_strings(['delta', 'epsilon'])
    print(f"  Observing: {event2}")
    kato_fixture.observe({'strings': event2, 'vectors': [], 'emotives': {}})
    
    # Check STM
    stm = kato_fixture.get_short_term_memory()
    print(f"STM before predictions: {stm}")
    print(f"Total strings: {sum(len(e) for e in stm)}")
    
    # Get predictions
    predictions = kato_fixture.get_predictions()
    print(f"\nNumber of predictions: {len(predictions)}")
    
    if predictions:
        print(f"First prediction: {predictions[0].get('name')}")
    else:
        print("NO PREDICTIONS!")
        # Try to understand why
        print(f"Processor ID: {kato_fixture.processor_id}")
        print(f"Base URL: {kato_fixture.base_url}")
        
    return predictions

if __name__ == "__main__":
    # Create fixture manually
    from fixtures.kato_fixtures import KATOTestFixture
    fixture = KATOTestFixture(processor_name="debug_test")
    fixture.setup()
    
    try:
        predictions = test_debug(fixture)
        print(f"\nTest completed. Got {len(predictions)} predictions")
    finally:
        fixture.teardown()