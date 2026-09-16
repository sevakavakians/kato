"""The Qdrant client APIs KATO depends on must exist.

qdrant-client 1.17 removed ``QdrantClient.search()``, which
``kato/storage/qdrant_store.py`` calls. On 1.17 that call raises AttributeError,
the surrounding ``except`` in ``QdrantStore.search`` swallows it, and
nearest-neighbour lookup silently returns nothing — so multimodal observations
stop resolving to their ``VCTR|`` symbols and predictions quietly lose matches,
with no error anywhere.

That is only caught end-to-end by a vector test that happens to depend on
nearest-neighbour recall. This checks the dependency directly, so a future
version bump fails immediately and says why.

Removing this test is the wrong fix; migrating ``qdrant_store.py`` to
``query_points()`` and then updating this test is the right one.
"""

import pytest
from qdrant_client import QdrantClient

# Methods kato/storage/qdrant_store.py calls on the client.
REQUIRED_CLIENT_METHODS = [
    "search",
    "upsert",
    "delete",
    "scroll",
    "retrieve",
    "create_collection",
    "delete_collection",
    "get_collection",
    "get_collections",
]


@pytest.mark.parametrize("method", REQUIRED_CLIENT_METHODS)
def test_qdrant_client_exposes_method(method):
    assert hasattr(QdrantClient, method), (
        f"qdrant-client no longer provides QdrantClient.{method}(), which "
        f"kato/storage/qdrant_store.py calls. QdrantStore catches the resulting "
        f"AttributeError, so this degrades silently rather than raising."
    )


def test_search_accepts_the_arguments_qdrant_store_passes():
    """QdrantStore.search passes these by keyword; a signature change breaks it."""
    import inspect

    sig = inspect.signature(QdrantClient.search)
    for param in ("collection_name", "query_vector", "limit", "query_filter",
                  "with_vectors", "with_payload", "score_threshold"):
        assert param in sig.parameters, (
            f"QdrantClient.search() no longer accepts '{param}'; "
            f"kato/storage/qdrant_store.py passes it by keyword."
        )
