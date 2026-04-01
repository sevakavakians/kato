"""
Utility KATO Operation Endpoints

Utility endpoints for pattern management, configuration, and processor data access.

Note: All core KATO operations (observe, learn, predictions) must now use
session-based endpoints under /sessions/{session_id}/.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request

router = APIRouter(tags=["kato-ops"])
logger = logging.getLogger('kato.api.kato_ops')


@router.get("/pattern/{pattern_id}")
async def get_pattern(
    request: Request,
    pattern_id: str = Path(..., description="Pattern ID to retrieve"),
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get a specific pattern by ID.

    Args:
        pattern_id: Pattern identifier (PTRN|<hash>)
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Pattern data and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        pattern = processor.get_pattern(pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")

        return {"pattern": pattern, "node_id": processor.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pattern {pattern_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pattern retrieval failed: {str(e)}")


@router.get("/percept-data")
async def get_percept_data(
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    DEPRECATED: Get current percept data from processor.

    This endpoint is deprecated in v3.0+ stateless architecture.
    Use session-based endpoint: GET /sessions/{session_id}/percept-data instead.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Empty percept data and deprecation warning
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    return {
        "percept_data": {},
        "node_id": processor.id,
        "warning": "This endpoint is deprecated. Use /sessions/{session_id}/percept-data for session-aware data."
    }


@router.get("/cognition-data")
async def get_cognition_data(
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    DEPRECATED: Get current cognition data from processor.

    This endpoint is deprecated in v3.0+ stateless architecture.
    Use session-based endpoint: GET /sessions/{session_id}/cognition-data instead.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Empty cognition data and deprecation warning
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    return {
        "cognition_data": {
            "predictions": [],
            "emotives": {},
            "symbols": [],
            "command": "",
            "metadata": {},
            "path": [],
            "strings": [],
            "vectors": [],
            "short_term_memory": []
        },
        "node_id": processor.id,
        "warning": "This endpoint is deprecated. Use /sessions/{session_id}/cognition-data for session-aware data."
    }


@router.get("/symbols/affinity")
async def get_all_symbol_affinities(
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get cumulative emotive affinity for all symbols in this node's knowledge base.

    Affinity is a running sum of averaged emotive values accumulated each time
    a pattern containing the symbol is learned with emotives.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Dictionary of symbol affinities and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        affinities = processor.pattern_processor.superkb.redis_writer.get_all_symbol_affinities()
        return {"affinities": affinities, "node_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting symbol affinities: {e}")
        raise HTTPException(status_code=500, detail=f"Symbol affinity retrieval failed: {str(e)}")


@router.get("/symbols/{symbol}/affinity")
async def get_symbol_affinity(
    request: Request,
    symbol: str = Path(..., description="Symbol name"),
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get cumulative emotive affinity for a specific symbol.

    Args:
        symbol: Symbol name
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Symbol affinity data and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        affinity = processor.pattern_processor.superkb.redis_writer.get_symbol_affinity(symbol)
        return {"symbol": symbol, "affinity": affinity, "node_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting affinity for symbol {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Symbol affinity retrieval failed: {str(e)}")


@router.get("/symbols/stats")
async def get_all_symbol_stats(
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get frequency and pattern member frequency (PMF) for all symbols in this node's knowledge base.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Dictionary of symbol stats and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        symbols = processor.pattern_processor.superkb.redis_writer.get_all_symbols_batch()
        return {"symbols": symbols, "node_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting symbol stats: {e}")
        raise HTTPException(status_code=500, detail=f"Symbol stats retrieval failed: {str(e)}")
