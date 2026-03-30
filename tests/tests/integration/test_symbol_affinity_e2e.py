"""
End-to-end integration tests for symbol affinity feature.

Tests the full flow: observe → learn with emotives → GET /symbols/affinity API.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_affinity_api_all_symbols(kato_fixture):
    """GET /symbols/affinity returns correct affinities after learning."""
    kato_fixture.clear_all_memory()

    # Learn pattern with emotives
    kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {'energy': 10}})
    kato_fixture.observe({'strings': ['beta'], 'vectors': [], 'emotives': {'energy': 10}})
    kato_fixture.learn()

    headers = {'X-Node-ID': kato_fixture.processor_id}
    response = kato_fixture.requests_session.get(
        f"{kato_fixture.base_url}/symbols/affinity",
        headers=headers
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    affinities = data['affinities']

    assert 'alpha' in affinities, f"alpha should be in affinities, got keys: {list(affinities.keys())}"
    assert 'beta' in affinities, f"beta should be in affinities, got keys: {list(affinities.keys())}"
    assert abs(affinities['alpha']['energy'] - 10.0) < 0.01
    assert abs(affinities['beta']['energy'] - 10.0) < 0.01


def test_affinity_api_single_symbol(kato_fixture):
    """GET /symbols/{symbol}/affinity returns correct affinity for one symbol."""
    kato_fixture.clear_all_memory()

    kato_fixture.observe({'strings': ['gamma'], 'vectors': [], 'emotives': {'trust': 5.0}})
    kato_fixture.observe({'strings': ['delta'], 'vectors': [], 'emotives': {'trust': 5.0}})
    kato_fixture.learn()

    headers = {'X-Node-ID': kato_fixture.processor_id}
    response = kato_fixture.requests_session.get(
        f"{kato_fixture.base_url}/symbols/gamma/affinity",
        headers=headers
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    assert data['symbol'] == 'gamma'
    assert abs(data['affinity']['trust'] - 5.0) < 0.01


def test_affinity_api_accumulates_across_learns(kato_fixture):
    """API reflects accumulated affinity after multiple learns."""
    kato_fixture.clear_all_memory()

    # First learn: [M, N] with utility=10
    kato_fixture.observe({'strings': ['M'], 'vectors': [], 'emotives': {'utility': 10}})
    kato_fixture.observe({'strings': ['N'], 'vectors': [], 'emotives': {'utility': 10}})
    kato_fixture.learn()

    # Start new session to reset emotives_accumulator
    kato_fixture.session_id = None

    # Second learn: [N, O] with utility=20
    kato_fixture.observe({'strings': ['N'], 'vectors': [], 'emotives': {'utility': 20}})
    kato_fixture.observe({'strings': ['O'], 'vectors': [], 'emotives': {'utility': 20}})
    kato_fixture.learn()

    headers = {'X-Node-ID': kato_fixture.processor_id}
    response = kato_fixture.requests_session.get(
        f"{kato_fixture.base_url}/symbols/affinity",
        headers=headers
    )
    assert response.status_code == 200

    affinities = response.json()['affinities']

    # M: only first learn -> 10
    assert abs(affinities['M']['utility'] - 10.0) < 0.01, f"M utility should be 10, got {affinities['M']}"

    # N: both learns -> 10 + 20 = 30
    assert abs(affinities['N']['utility'] - 30.0) < 0.01, f"N utility should be 30, got {affinities['N']}"

    # O: only second learn -> 20
    assert abs(affinities['O']['utility'] - 20.0) < 0.01, f"O utility should be 20, got {affinities['O']}"


def test_affinity_api_nonexistent_symbol(kato_fixture):
    """GET /symbols/{symbol}/affinity returns empty affinity for unknown symbol."""
    kato_fixture.clear_all_memory()

    headers = {'X-Node-ID': kato_fixture.processor_id}
    response = kato_fixture.requests_session.get(
        f"{kato_fixture.base_url}/symbols/nonexistent_symbol_xyz/affinity",
        headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data['affinity'] == {}, f"Nonexistent symbol should have empty affinity, got {data['affinity']}"
