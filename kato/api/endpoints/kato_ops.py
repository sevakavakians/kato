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


@router.post("/genes/update")
async def update_genes(
    genes_data: dict[str, Any],
    request: Request,
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Update processor genes/configuration.

    Args:
        genes_data: Dictionary of gene names and values to update
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Status and updated genes
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        # Extract genes from request body (handles both direct and nested formats)
        genes = genes_data.get('genes', genes_data)

        # Update genome manifest
        for key, value in genes.items():
            key_lower = key.lower()
            if hasattr(processor, 'genome_manifest'):
                processor.genome_manifest[key_lower] = value
                logger.info(f"Updated gene {key} = {value}")

            # Update processor attributes directly for immediate effect
            if key_lower == 'max_pattern_length':
                processor.MAX_PATTERN_LENGTH = value
                if hasattr(processor, 'observation_processor'):
                    processor.observation_processor.max_pattern_length = value
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.max_pattern_length = value
            elif key_lower == 'stm_mode':
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.stm_mode = value
                    logger.info(f"Updated pattern_processor.stm_mode to {value}")
            elif key_lower == 'recall_threshold':
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.recall_threshold = value
                    # Also update the searcher if it exists
                    if hasattr(processor.pattern_processor, 'patterns_searcher'):
                        processor.pattern_processor.patterns_searcher.recall_threshold = value
                    logger.info(f"Updated pattern_processor.recall_threshold to {value}")

        return {"status": "okay", "node_id": processor.id, "genes": genes_data}
    except Exception as e:
        logger.error(f"Error updating genes: {e}")
        raise HTTPException(status_code=500, detail=f"Gene update failed: {str(e)}")


@router.get("/gene/{gene_name}")
async def get_gene(
    request: Request,
    gene_name: str = Path(..., description="Gene name to retrieve"),
    node_id: Optional[str] = Query(None, description="Node identifier")
):
    """
    Get a specific gene value.

    Args:
        gene_name: Name of the gene to retrieve
        node_id: Node identifier (defaults to header-based node_id)

    Returns:
        Gene name, value, and node_id
    """
    from kato.services.kato_fastapi import app_state, get_node_id_from_request

    # Use header-based node ID if not provided
    if node_id is None:
        node_id = get_node_id_from_request(request)

    processor = await app_state.processor_manager.get_processor(node_id)

    try:
        if hasattr(processor, 'genome_manifest'):
            value = processor.genome_manifest.get(gene_name.lower())
            if value is not None:
                return {"gene": gene_name, "value": value, "node_id": processor.id}

        raise HTTPException(status_code=404, detail=f"Gene {gene_name} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting gene {gene_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Gene retrieval failed: {str(e)}")


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
