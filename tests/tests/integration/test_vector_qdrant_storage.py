#!/usr/bin/env python3
"""
Integration tests for vector storage and Qdrant.

These tests verify that vectors are actually stored in Qdrant and that
similarity search works end-to-end, including the VCTR|hash → UUID conversion,
reverse mapping, large vectors, and similarity-based predictions.
"""

import os
import random
import sys
import uuid

import numpy as np
import requests

# Add path for fixtures
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture


def test_vector_id_deterministic():
    """Verify that the same VCTR|hash always produces the same UUID (uuid5 is deterministic)."""
    from kato.searches.vector_search_engine import _vctr_name_to_qdrant_id

    vctr_name = "VCTR|7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"
    id1 = _vctr_name_to_qdrant_id(vctr_name)
    id2 = _vctr_name_to_qdrant_id(vctr_name)

    assert id1 == id2, "Same VCTR name should produce same UUID"
    # Verify it's a valid UUID
    parsed = uuid.UUID(id1)
    assert str(parsed) == id1

    # Different names produce different UUIDs
    other_name = "VCTR|0000000000000000000000000000000000000000"
    id3 = _vctr_name_to_qdrant_id(other_name)
    assert id3 != id1, "Different VCTR names should produce different UUIDs"


def test_vectors_stored_in_qdrant(kato_fixture):
    """Train with vectors, then verify they actually exist in Qdrant."""
    kato_fixture.clear_all_memory()

    # Create a sequence with vectors
    observations = [
        {
            'strings': ['alpha'],
            'vectors': [[1.0, 0.0, 0.0, 0.0]],
            'emotives': {}
        },
        {
            'strings': ['beta'],
            'vectors': [[0.0, 1.0, 0.0, 0.0]],
            'emotives': {}
        },
        {
            'strings': ['gamma'],
            'vectors': [[0.0, 0.0, 1.0, 0.0]],
            'emotives': {}
        },
    ]

    for obs in observations:
        kato_fixture.observe(obs)

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None, "Learning should succeed"

    # Now check Qdrant directly for this processor's collection
    processor_id = kato_fixture.processor_id
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_headers = {}
    qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
    if qdrant_api_key:
        qdrant_headers["api-key"] = qdrant_api_key

    # Find the collection matching this processor_id (may have suffix like _kato)
    collections_resp = requests.get(f"{qdrant_url}/collections", headers=qdrant_headers)
    assert collections_resp.status_code == 200, "Should be able to list Qdrant collections"
    all_collections = [c['name'] for c in collections_resp.json()['result']['collections']]
    matching = [c for c in all_collections if processor_id in c]
    assert len(matching) > 0, (
        f"No Qdrant collection found containing processor_id '{processor_id}'. "
        f"Existing collections: {all_collections}"
    )
    collection_name = matching[0]

    resp = requests.get(f"{qdrant_url}/collections/{collection_name}", headers=qdrant_headers)
    assert resp.status_code == 200, f"Collection {collection_name} should exist in Qdrant"

    info = resp.json()
    points_count = info['result']['points_count']
    assert points_count >= 3, (
        f"Expected at least 3 vectors in Qdrant collection, got {points_count}"
    )
    print(f"Verified {points_count} vectors stored in Qdrant collection {collection_name}")


def test_search_returns_vctr_names(kato_fixture):
    """Store vectors, search for similar one, verify returned IDs are VCTR|hash format."""
    kato_fixture.clear_all_memory()

    # Store vectors
    observations = [
        {
            'strings': ['point_a'],
            'vectors': [[1.0, 0.0, 0.0, 0.0]],
            'emotives': {}
        },
        {
            'strings': ['point_b'],
            'vectors': [[0.0, 1.0, 0.0, 0.0]],
            'emotives': {}
        },
    ]

    for obs in observations:
        kato_fixture.observe(obs)

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Now observe a similar vector and check predictions
    # The VCTR names in predictions should be in VCTR|hash format, not UUIDs
    kato_fixture.clear_stm()

    kato_fixture.observe({
        'strings': [],
        'vectors': [[0.95, 0.05, 0.0, 0.0]],  # Similar to point_a's vector
        'emotives': {}
    })

    # Check STM to see what vector names were resolved
    stm = kato_fixture.get_stm()
    if stm:
        # Look for VCTR| prefixed names in STM
        all_symbols = []
        for event in stm:
            if isinstance(event, list):
                all_symbols.extend(event)
            else:
                all_symbols.append(str(event))

        vctr_symbols = [s for s in all_symbols if str(s).startswith('VCTR|')]
        for sym in vctr_symbols:
            # Should be VCTR|hash format, not a UUID
            assert '|' in str(sym), f"Vector ID should be VCTR|hash format, got: {sym}"
            # Should NOT look like a UUID
            hash_part = str(sym).split('|', 1)[1]
            try:
                uuid.UUID(hash_part)
                assert False, f"Vector ID hash part should NOT be a UUID: {sym}"
            except ValueError:
                pass  # Good - it's a SHA1 hash, not a UUID
        print(f"Verified {len(vctr_symbols)} VCTR symbols in STM have correct format")


def test_similarity_prediction_accuracy(kato_fixture):
    """End-to-end: train with labeled vectors, observe similar vector, verify correct prediction."""
    kato_fixture.clear_all_memory()

    # Train: 3 distinct vectors each paired with a label
    # Pattern: [label, VCTR] → learn as a pattern
    training_sequences = [
        [
            {'strings': ['cat'], 'vectors': [[1.0, 0.0, 0.0, 0.0]], 'emotives': {}},
            {'strings': ['meow'], 'vectors': [], 'emotives': {}},
        ],
        [
            {'strings': ['dog'], 'vectors': [[0.0, 1.0, 0.0, 0.0]], 'emotives': {}},
            {'strings': ['bark'], 'vectors': [], 'emotives': {}},
        ],
        [
            {'strings': ['bird'], 'vectors': [[0.0, 0.0, 1.0, 0.0]], 'emotives': {}},
            {'strings': ['chirp'], 'vectors': [], 'emotives': {}},
        ],
    ]

    for seq in training_sequences:
        kato_fixture.clear_stm()
        for obs in seq:
            kato_fixture.observe(obs)
        pattern_name = kato_fixture.learn()
        assert pattern_name is not None, "Learning should succeed"

    # Now observe a vector similar to 'cat' (close to [1,0,0,0])
    kato_fixture.clear_stm()
    kato_fixture.observe({
        'strings': ['cat'],
        'vectors': [[0.95, 0.05, 0.0, 0.0]],
        'emotives': {}
    })

    predictions = kato_fixture.get_predictions()

    # Extract all predicted symbols from future
    predicted_symbols = set()
    for pred in predictions:
        if 'future' in pred:
            for future_item in pred['future']:
                if isinstance(future_item, list):
                    predicted_symbols.update(future_item)
                elif isinstance(future_item, str):
                    predicted_symbols.add(future_item)

    # Should predict 'meow' (the label paired with the cat vector)
    assert 'meow' in predicted_symbols, (
        f"Should predict 'meow' after observing cat-like vector. Got predictions: {predicted_symbols}"
    )
    print(f"Correctly predicted 'meow' from similar vector. All predictions: {predicted_symbols}")


def test_large_vector_handling(kato_fixture):
    """Test handling of larger dimensional vectors (128-dim)."""
    kato_fixture.clear_all_memory()

    large_dim = 128
    large_vector = [random.random() for _ in range(large_dim)]

    result = kato_fixture.observe({
        'strings': ['large_vector_test'],
        'vectors': [large_vector],
        'emotives': {}
    })
    assert result['status'] in ['ok', 'okay', 'observed']

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None, f"Should learn pattern with {large_dim}-dim vector"
