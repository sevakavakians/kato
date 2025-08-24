"""
Helper functions for KATO tests.
Provides utilities for handling KATO's specific behaviors.
"""

def sort_event_strings(event):
    """
    Sort strings within an event alphanumerically as KATO does.
    
    KATO sorts strings alphanumerically within each event/observation,
    but preserves the order of events in a sequence.
    
    Args:
        event: A list of strings representing a single event
        
    Returns:
        The same list with strings sorted alphanumerically
    """
    if isinstance(event, list):
        return sorted(event)
    return event


def sort_events_strings(events):
    """
    Sort strings within each event in a list of events.
    
    Args:
        events: A list of events, where each event is a list of strings
        
    Returns:
        The same structure with strings sorted within each event
    """
    if isinstance(events, list):
        return [sort_event_strings(event) for event in events]
    return events


def assert_working_memory_equals(actual_wm, expected_events):
    """
    Assert that working memory matches expected events, accounting for KATO's sorting.
    
    Args:
        actual_wm: The actual working memory from KATO
        expected_events: The expected events (will be sorted for comparison)
    """
    sorted_expected = sort_events_strings(expected_events)
    assert actual_wm == sorted_expected, \
        f"Working memory mismatch:\nActual:   {actual_wm}\nExpected: {sorted_expected}"