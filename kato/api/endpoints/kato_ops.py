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
    Get current percept data from processor.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Percept data and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        percept_data = processor.get_percept_data()
        return {"percept_data": percept_data, "node_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting percept data: {e}")
        raise HTTPException(status_code=500, detail=f"Percept data retrieval failed: {str(e)}")


@router.get("/cognition-data")
async def get_cognition_data(
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get current cognition data from processor.

    Args:
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Cognition data and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        cognition_data = processor.cognition_data
        return {"cognition_data": cognition_data, "node_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting cognition data: {e}")
        raise HTTPException(status_code=500, detail=f"Cognition data retrieval failed: {str(e)}")
