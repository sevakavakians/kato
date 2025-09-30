"""
Primary KATO Operation Endpoints

Core endpoints for observations, learning, predictions, and pattern management.
These are the main KATO functionality endpoints.
"""

import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Query, Path
from ..schemas import (
    ObservationData, ObservationResult, STMResponse, LearnResult, 
    PredictionsResponse, ObservationSequenceRequest, ObservationSequenceResult
)

router = APIRouter(tags=["kato-ops"])
logger = logging.getLogger('kato.api.kato_ops')


@router.post("/observe", response_model=ObservationResult)
async def observe_primary(
    data: ObservationData,
    processor_id: Optional[str] = Query(None, description="Processor identifier")
):
    """
    Process a new observation.
    
    Accepts multi-modal input (strings, vectors, emotives) and processes it
    through the KATO system, updating short-term memory and triggering 
    auto-learning if configured.
    """
    from kato.services.kato_fastapi import app_state
    
    try:
        logger.debug(f"Processing observation for processor {processor_id}")
        processor = await app_state.processor_manager.get_processor_by_id(processor_id)
        
        observation = {
            'strings': data.strings,
            'vectors': data.vectors,
            'emotives': data.emotives,
            'unique_id': f"obs-{uuid.uuid4().hex}",
            'source': 'primary'
        }
        
        result = processor.observe(observation)
        stm_length = len(processor.get_stm())
        
        return ObservationResult(
            status="okay",
            processor_id=processor.id,
            stm_length=stm_length,
            time=processor.time,
            unique_id=result.get('unique_id', ''),
            auto_learned_pattern=result.get('auto_learned_pattern')
        )
    except Exception as e:
        logger.error(f"Error processing observation: {e}")
        raise HTTPException(status_code=500, detail=f"Observation failed: {str(e)}")


@router.get("/stm", response_model=STMResponse, aliases=["/short-term-memory"])
async def get_stm_primary(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """Get short-term memory for the processor"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    stm = processor.get_stm()
    
    return STMResponse(
        stm=stm,
        processor_id=processor.id,
        length=len(stm)
    )


@router.post("/learn", response_model=LearnResult)
async def learn_primary(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """
    Learn a pattern from the current STM.
    
    Takes all observations currently in short-term memory and creates
    a persistent pattern that can be used for future predictions.
    """
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    stm = processor.get_stm()
    
    if not stm:
        raise HTTPException(status_code=400, detail="Cannot learn from empty STM")
    
    logger.info(f"Learning pattern from {len(stm)} events")
    
    try:
        pattern_name = processor.learn()
        final_stm = processor.get_stm()
        
        return LearnResult(
            status="learned",
            pattern_name=pattern_name,
            processor_id=processor.id,
            message=f"Learned pattern {pattern_name} from {len(stm)} events"
        )
    except Exception as e:
        logger.error(f"Error learning pattern: {e}")
        raise HTTPException(status_code=500, detail=f"Learning failed: {str(e)}")


@router.post("/clear-stm", aliases=["/clear-short-term-memory"])
async def clear_stm_primary(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """Clear the short-term memory"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        processor.clear_short_term_memory()
        return {"status": "cleared", "processor_id": processor.id}
    except Exception as e:
        logger.error(f"Error clearing STM: {e}")
        raise HTTPException(status_code=500, detail=f"Clear STM failed: {str(e)}")


@router.post("/clear-all")
async def clear_all_primary(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """
    Clear all processor state including STM, patterns, and symbols.
    
    WARNING: This will delete all learned knowledge for this processor.
    Use with caution in production environments.
    """
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        await processor.clear_all()
        return {"status": "cleared", "processor_id": processor.id, "message": "All data cleared"}
    except Exception as e:
        logger.error(f"Error clearing all data: {e}")
        raise HTTPException(status_code=500, detail=f"Clear all failed: {str(e)}")


@router.get("/predictions", response_model=PredictionsResponse)
async def get_predictions_primary(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """
    Get predictions based on current STM.
    
    Analyzes the current short-term memory and returns potential
    future sequences based on learned patterns.
    """
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        predictions = processor.get_predictions()
        
        # Get future_potentials from the pattern processor if available
        future_potentials = None
        if hasattr(processor.pattern_processor, 'future_potentials'):
            future_potentials = processor.pattern_processor.future_potentials
        
        return PredictionsResponse(
            predictions=predictions,
            future_potentials=future_potentials,
            processor_id=processor.id,
            count=len(predictions)
        )
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail=f"Predictions failed: {str(e)}")


@router.post("/genes/update")
async def update_genes(
    genes_data: Dict[str, Any],
    processor_id: Optional[str] = Query(None, description="Processor identifier")
):
    """Update processor genes/configuration"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        # Update genome manifest
        for key, value in genes_data.items():
            if hasattr(processor, 'genome_manifest'):
                processor.genome_manifest[key.upper()] = value
                logger.info(f"Updated gene {key} = {value}")
            
            # Update processor attributes directly for immediate effect
            if key.lower() == 'max_pattern_length':
                processor.MAX_PATTERN_LENGTH = value
                if hasattr(processor, 'observation_processor'):
                    processor.observation_processor.max_pattern_length = value
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.max_pattern_length = value
        
        return {"status": "updated", "processor_id": processor.id, "genes": genes_data}
    except Exception as e:
        logger.error(f"Error updating genes: {e}")
        raise HTTPException(status_code=500, detail=f"Gene update failed: {str(e)}")


@router.get("/gene/{gene_name}")
async def get_gene(
    gene_name: str = Path(..., description="Gene name to retrieve"),
    processor_id: Optional[str] = Query(None, description="Processor identifier")
):
    """Get a specific gene value"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        if hasattr(processor, 'genome_manifest'):
            value = processor.genome_manifest.get(gene_name.upper())
            if value is not None:
                return {"gene": gene_name, "value": value, "processor_id": processor.id}
        
        raise HTTPException(status_code=404, detail=f"Gene {gene_name} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting gene {gene_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Gene retrieval failed: {str(e)}")


@router.get("/pattern/{pattern_id}")
async def get_pattern(
    pattern_id: str = Path(..., description="Pattern ID to retrieve"),
    processor_id: Optional[str] = Query(None, description="Processor identifier")
):
    """Get a specific pattern by ID"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        pattern = await processor.storage_manager.mongo_manager.get_pattern(pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
        
        return {"pattern": pattern, "processor_id": processor.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pattern {pattern_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pattern retrieval failed: {str(e)}")


@router.get("/percept-data")
async def get_percept_data(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """Get current percept data from processor"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        percept_data = processor.get_percept_data()
        return {"percept_data": percept_data, "processor_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting percept data: {e}")
        raise HTTPException(status_code=500, detail=f"Percept data retrieval failed: {str(e)}")


@router.get("/cognition-data")
async def get_cognition_data(processor_id: Optional[str] = Query(None, description="Processor identifier")):
    """Get current cognition data from processor"""
    from kato.services.kato_fastapi import app_state
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        cognition_data = processor.get_cognition_data()
        return {"cognition_data": cognition_data, "processor_id": processor.id}
    except Exception as e:
        logger.error(f"Error getting cognition data: {e}")
        raise HTTPException(status_code=500, detail=f"Cognition data retrieval failed: {str(e)}")


@router.post("/observe-sequence", response_model=ObservationSequenceResult)
async def observe_sequence_primary(
    request: ObservationSequenceRequest,
    processor_id: Optional[str] = Query(None, description="Processor identifier")
):
    """
    Process multiple observations in sequence with optional isolation.
    
    Provides bulk processing capabilities with options for:
    - Sequential processing with shared STM context
    - Isolated processing where each observation gets fresh STM
    - Auto-learning after the sequence completes
    """
    from kato.services.kato_fastapi import app_state
    
    if not request.observations:
        raise HTTPException(status_code=400, detail="No observations provided")
    
    processor = await app_state.processor_manager.get_processor_by_id(processor_id)
    
    try:
        logger.info(f"Processing sequence of {len(request.observations)} observations")
        
        results = []
        initial_stm_length = len(processor.get_stm())
        auto_learned_patterns = []
        
        for i, obs_data in enumerate(request.observations):
            # Clear STM before each observation if isolation requested
            if request.isolated and i > 0:
                processor.clear_short_term_memory()
                logger.debug(f"Cleared STM for isolated observation {i}")
            
            observation = {
                'strings': obs_data.strings,
                'vectors': obs_data.vectors,
                'emotives': obs_data.emotives,
                'unique_id': f"seq-obs-{uuid.uuid4().hex}",
                'source': 'sequence'
            }
            
            result = processor.observe(observation)
            
            # Track auto-learned patterns
            if result.get('auto_learned_pattern'):
                auto_learned_patterns.append(result['auto_learned_pattern'])
            
            observation_result = {
                "status": "okay",
                "sequence_position": i,
                "stm_length": len(processor.get_stm()),
                "time": processor.time,
                "unique_id": result.get('unique_id', ''),
                "auto_learned_pattern": result.get('auto_learned_pattern')
            }
            results.append(observation_result)
        
        # Learn from final STM if requested and STM is not empty
        final_learned_pattern = None
        if request.learn_after_sequence:
            final_stm = processor.get_stm()
            if final_stm:
                try:
                    final_learned_pattern = processor.learn()
                    logger.info(f"Learned final pattern: {final_learned_pattern}")
                except Exception as learn_error:
                    logger.warning(f"Failed to learn final pattern: {learn_error}")
        
        final_stm_length = len(processor.get_stm())
        
        return ObservationSequenceResult(
            status="completed",
            processor_id=processor.id,
            observations_processed=len(request.observations),
            initial_stm_length=initial_stm_length,
            final_stm_length=final_stm_length,
            results=results,
            auto_learned_patterns=auto_learned_patterns,
            final_learned_pattern=final_learned_pattern,
            isolated=request.isolated
        )
        
    except Exception as e:
        logger.error(f"Error processing observation sequence: {e}")
        raise HTTPException(status_code=500, detail=f"Sequence processing failed: {str(e)}")