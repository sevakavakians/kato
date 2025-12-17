#!/usr/bin/env python3
"""
Manual test script for inspecting emotives merging behavior.

This script replicates the test_emotives_merging_on_relearning_same_pattern test
but WITHOUT pytest teardown, allowing manual inspection of the knowledgebase data.

Usage:
    python scripts/manual_emotives_inspection.py

The script will create a session, perform the test operations, and print
instructions for manually inspecting the data in Redis and ClickHouse.

Data will persist until you manually clean it up.
"""

import hashlib
import json
import sys
import requests
import redis


# Configuration
BASE_URL = "http://localhost:8000"
NODE_ID = "emotives_inspection"
BASE_ID = "kato"


def get_kb_id(node_id: str, base_id: str = "kato") -> str:
    """
    Calculate the actual kb_id used by ProcessorManager after truncation.

    This replicates the logic from ProcessorManager._get_processor_id() to ensure
    we query Redis/ClickHouse with the same kb_id that was used for storage.

    Args:
        node_id: The node identifier
        base_id: Base processor ID (default: "kato")

    Returns:
        The actual kb_id after truncation (if needed)
    """
    # Clean node_id (remove unsafe characters)
    safe_node_id = node_id
    for char in ['/', '\\', '.', '"', '$', '*', '<', '>', ':', '|', '?', '-', ' ']:
        safe_node_id = safe_node_id.replace(char, '_')

    # Clean base_id
    safe_base_id = base_id.replace('-', '_')

    # Check if truncation is needed (60 char limit)
    full_name = f"{safe_node_id}_{safe_base_id}"

    if len(full_name) > 60:
        # Truncate using same logic as ProcessorManager
        node_hash = hashlib.md5(safe_node_id.encode(), usedforsecurity=False).hexdigest()[:8]
        max_node_length = 60 - len(safe_base_id) - 1 - 8 - 1
        truncated_node = safe_node_id[:max_node_length]
        return f"{truncated_node}_{node_hash}_{safe_base_id}"

    return full_name


def get_redis_emotives(kb_id: str, pattern_name: str) -> list[dict] | None:
    """
    Get emotives directly from Redis.

    Args:
        kb_id: The knowledge base identifier
        pattern_name: Pattern name (with or without PTRN| prefix)

    Returns:
        List of emotive dicts if found, None if key doesn't exist
    """
    # Strip PTRN| prefix if present
    clean_name = pattern_name[5:] if pattern_name.startswith('PTRN|') else pattern_name

    # Connect to Redis
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # Query emotives key
    emotives_key = f"{kb_id}:emotives:{clean_name}"
    emotives_value = redis_client.get(emotives_key)

    if emotives_value is None:
        return None

    return json.loads(emotives_value)


def main():
    """Run the emotives merging test manually."""

    print("=" * 80)
    print("KATO Emotives Merging Test - Manual Inspection Mode")
    print("=" * 80)
    print()

    # Calculate kb_id
    kb_id = get_kb_id(NODE_ID, BASE_ID)
    print(f"Configuration:")
    print(f"  Base URL:  {BASE_URL}")
    print(f"  Node ID:   {NODE_ID}")
    print(f"  KB ID:     {kb_id}")
    print()

    # Step 1: Create session
    print("Step 1: Creating session...")
    try:
        response = requests.post(f"{BASE_URL}/sessions", json={"node_id": NODE_ID})
        response.raise_for_status()
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"  ✓ Session created: {session_id}")
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Failed to create session: {e}")
        print("\nMake sure KATO services are running:")
        print("  ./start.sh")
        sys.exit(1)

    print()

    # Step 2: Clear all memory (start fresh)
    print("Step 2: Clearing all memory...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/clear-all")
    response.raise_for_status()
    print("  ✓ Memory cleared")
    print()

    # Step 3: First learning - X (mood=0.9) → Y (mood=0.8)
    print("Step 3: First learning - X → Y with emotives [0.9, 0.8]...")

    # Observe X with mood=0.9
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['X'], 'vectors': [], 'emotives': {'mood': 0.9}}
    )
    response.raise_for_status()
    print("  ✓ Observed: X (mood=0.9)")

    # Observe Y with mood=0.8
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['Y'], 'vectors': [], 'emotives': {'mood': 0.8}}
    )
    response.raise_for_status()
    print("  ✓ Observed: Y (mood=0.8)")

    # Learn pattern
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/learn", json={})
    response.raise_for_status()
    learn_data = response.json()
    pattern_name_1 = learn_data.get("pattern_name", "")
    print(f"  ✓ Pattern learned: {pattern_name_1}")

    # Validate first learning
    emotives_1 = get_redis_emotives(kb_id, pattern_name_1)
    if emotives_1 and len(emotives_1) == 2:
        print(f"  ✓ Redis emotives validated: {emotives_1}")
    else:
        print(f"  ✗ Unexpected emotives: {emotives_1}")

    print()

    # Step 4: Clear STM only (keep LTM)
    print("Step 4: Clearing short-term memory (STM)...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/clear-stm", json={})
    response.raise_for_status()
    print("  ✓ STM cleared (LTM preserved)")
    print()

    # Step 5: Second learning - X (mood=0.5) → Y (mood=0.3)
    print("Step 5: Second learning - X → Y with emotives [0.5, 0.3]...")

    # Observe X with mood=0.5
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['X'], 'vectors': [], 'emotives': {'mood': 0.5}}
    )
    response.raise_for_status()
    print("  ✓ Observed: X (mood=0.5)")

    # Observe Y with mood=0.3
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['Y'], 'vectors': [], 'emotives': {'mood': 0.3}}
    )
    response.raise_for_status()
    print("  ✓ Observed: Y (mood=0.3)")

    # Learn pattern again
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/learn", json={})
    response.raise_for_status()
    learn_data = response.json()
    pattern_name_2 = learn_data.get("pattern_name", "")
    print(f"  ✓ Pattern learned: {pattern_name_2}")

    # Validate pattern names match
    clean_name_1 = pattern_name_1[5:] if pattern_name_1.startswith('PTRN|') else pattern_name_1
    clean_name_2 = pattern_name_2[5:] if pattern_name_2.startswith('PTRN|') else pattern_name_2

    if clean_name_1 == clean_name_2:
        print(f"  ✓ Pattern names match (same pattern re-learned)")
    else:
        print(f"  ✗ Pattern names differ!")
        print(f"    First:  {clean_name_1}")
        print(f"    Second: {clean_name_2}")

    
    ## ----
    # Step : Clear STM only (keep LTM)
    print("Step 4: Clearing short-term memory (STM)...")
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/clear-stm", json={})
    response.raise_for_status()
    print("  ✓ STM cleared (LTM preserved)")
    print()

    # Step : Third learning - X (mood=0.5) → Y (mood=0.3)
    print("Step : Third learning ")

    # Observe X with mood=0.5
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['X'], 'vectors': [], 'emotives': {'mood': 5, 'power': 100}}
    )
    response.raise_for_status()
    print("  ✓ Observed: X (mood=0.5)")

    # Observe Y with mood=0.3
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['Y'], 'vectors': [], 'emotives': {'mood': 6, 'taste': -2344}}
    )
    response.raise_for_status()
    # Observe
    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={'strings': ['Z'], 'vectors': [], 'emotives': {'mood': 7, 'power': -200}, 'metadata': {'source': 'manual_test'} }
    )
    response.raise_for_status()
    

    # Learn pattern again
    response = requests.post(f"{BASE_URL}/sessions/{session_id}/learn", json={})
    response.raise_for_status()
    learn_data = response.json()
    pattern_name_3 = learn_data.get("pattern_name", "")
    print(f"  ✓ Pattern learned: {pattern_name_3}")




    # Validate emotives merged
    emotives_2 = get_redis_emotives(kb_id, pattern_name_2)
    if emotives_2 and len(emotives_2) == 4:
        print(f"  ✓ Emotives merged successfully: {emotives_2}")

        # Validate order
        expected = [
            {'mood': 0.9},  # First learning, first emotive
            {'mood': 0.8},  # First learning, second emotive
            {'mood': 0.5},  # Second learning, first emotive
            {'mood': 0.3}   # Second learning, second emotive
        ]

        if emotives_2 == expected:
            print(f"  ✓ Emotives order correct!")
        else:
            print(f"  ✗ Emotives order incorrect!")
            print(f"    Expected: {expected}")
            print(f"    Got:      {emotives_2}")
    else:
        print(f"  ✗ Unexpected emotives count: {len(emotives_2) if emotives_2 else 0}")
        print(f"    Emotives: {emotives_2}")

    print()

    # Step 6: Print inspection instructions
    print("=" * 80)
    print("TEST COMPLETE - Data Ready for Inspection")
    print("=" * 80)
    print()
    print("Session Details:")
    print(f"  Session ID:    {session_id}")
    print(f"  Node ID:       {NODE_ID}")
    print(f"  KB ID:         {kb_id}")
    print(f"  Pattern Name:  {clean_name_2}")
    print()

    print("=" * 80)
    print("MANUAL INSPECTION COMMANDS")
    print("=" * 80)
    print()

    print("Redis - Emotives:")
    print(f"  redis-cli")
    print(f"  > GET {kb_id}:emotives:{clean_name_2}")
    print()

    print("Redis - Frequency:")
    print(f"  redis-cli")
    print(f"  > GET {kb_id}:freq:{clean_name_2}")
    print()

    print("Redis - Metadata:")
    print(f"  redis-cli")
    print(f"  > GET {kb_id}:metadata:{clean_name_2}")
    print()

    print("Redis - List all keys for this KB:")
    print(f"  redis-cli")
    print(f"  > KEYS {kb_id}:*")
    print()

    print("ClickHouse - Pattern data:")
    print(f"  clickhouse-client")
    print(f"  > SELECT * FROM kato.patterns_data WHERE kb_id = '{kb_id}' AND name = '{clean_name_2}' FORMAT Vertical;")
    print()

    print("ClickHouse - All patterns for this KB:")
    print(f"  clickhouse-client")
    print(f"  > SELECT kb_id, name, frequency, created_at FROM kato.patterns_data WHERE kb_id = '{kb_id}' FORMAT Vertical;")
    print()

    print("=" * 80)
    print("CLEANUP WHEN DONE")
    print("=" * 80)
    print()
    print("To clean up the data when you're done inspecting:")
    print()
    print(f"  curl -X POST {BASE_URL}/sessions/{session_id}/clear-all")
    print()
    print("Or delete the session entirely:")
    print()
    print(f"  curl -X DELETE {BASE_URL}/sessions/{session_id}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
