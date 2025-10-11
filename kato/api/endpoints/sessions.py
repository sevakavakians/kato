"""
Session Management Endpoints

Handles session creation, management, and session-scoped KATO operations.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from kato.api.schemas import (
    CreateSessionRequest,
    LearnResult,
    ObservationData,
    ObservationResult,
    ObservationSequenceRequest,
    ObservationSequenceResult,
    PredictionsResponse,
    SessionResponse,
    STMResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger('kato.api.sessions')


@router.get("/test/{test_id}")
async def test_endpoint(test_id: str):
    """Simple test endpoint to verify routing works"""
    logger.debug(f"Test endpoint called: {test_id}")
    return {"test_id": test_id, "message": "endpoint works"}


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    Create a new isolated session for a user.

    This enables multiple users to use KATO simultaneously
    without any data collision.
    """
    logger.debug(f"create_session endpoint called with node_id: {request.node_id}")
    from kato.services.kato_fastapi import app_state

    logger.info(f"Creating session with manager id: {id(app_state.session_manager)}")
    logger.debug(f"Calling session_manager.create_session for node: {request.node_id}")
    session = await app_state.session_manager.create_session(
        node_id=request.node_id,
        config=request.config,
        metadata=request.metadata,
        ttl_seconds=request.ttl_seconds
    )
    logger.debug(f"Session created: {session.session_id}")

    return SessionResponse(
        session_id=session.session_id,
        node_id=session.node_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        ttl_seconds=request.ttl_seconds or 3600,  # Use provided TTL or default
        metadata=session.metadata,
        session_config=session.session_config.get_config_only() if hasattr(session, 'session_config') else {}
    )


@router.get("/count")
async def get_active_session_count():
    """Get the count of active sessions"""
    from kato.services.kato_fastapi import app_state

    logger.debug("Getting active session count")
    try:
        count = await app_state.session_manager.get_active_session_count_async()
        return {"active_session_count": count}
    except Exception as e:
        logger.error(f"Error getting session count: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session count")


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_info(session_id: str):
    """Get information about a session"""
    from kato.services.kato_fastapi import app_state

    logger.info(f"Getting session info for: {session_id}")
    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # Calculate TTL from expires_at - current time
    ttl_seconds = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())

    return SessionResponse(
        session_id=session.session_id,
        node_id=session.node_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        ttl_seconds=max(0, ttl_seconds),  # Ensure non-negative
        metadata=session.metadata,
        session_config=session.session_config.get_config_only() if hasattr(session, 'session_config') else {}
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    from kato.services.kato_fastapi import app_state

    deleted = await app_state.session_manager.delete_session(session_id)

    if not deleted:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    return {"status": "deleted", "session_id": session_id}


@router.post("/{session_id}/config")
async def update_session_config(session_id: str, request_data: dict[str, Any]):
    """Update session configuration (genes/parameters)"""
    from kato.services.kato_fastapi import app_state

    logger.error(f"!!! DEBUG: update_session_config called for {session_id} with: {request_data}")
    logger.info(f"Updating config for session {session_id} with data: {request_data}")

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    # Extract config from request - it comes as {"config": {...}}
    config = request_data.get('config', request_data)
    logger.info(f"Extracted config: {config}")

    # Update the session's config - using SessionConfiguration's update method
    for key, value in config.items():
        if hasattr(session.session_config, key):
            setattr(session.session_config, key, value)
            logger.info(f"Updated session config {key} = {value}")
        else:
            logger.warning(f"Session config does not have attribute {key}")

    # Save the updated session back to Redis
    logger.info("Saving updated session to Redis")
    await app_state.session_manager.update_session(session)
    logger.info("Session saved successfully")

    # Try to get processor if it exists, otherwise it will be created with new config on next observation
    processor = None
    try:
        processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)
    except Exception as e:
        # Processor doesn't exist yet, will be created with new config on next observation
        logger.info(f"Processor not yet created for node {session.node_id}, config will be applied on first observation: {e}")

    if processor:
        # Apply configuration dynamically to processor
        for key, value in config.items():
            if key == 'max_pattern_length':
                processor.genome_manifest['MAX_PATTERN_LENGTH'] = value
                processor.MAX_PATTERN_LENGTH = value  # Update the processor's attribute directly
                # Also update the observation processor's max_pattern_length for auto-learning
                if hasattr(processor, 'observation_processor'):
                    processor.observation_processor.max_pattern_length = value
                    logger.info(f"Updated observation_processor.max_pattern_length to {value}")
                # And update the pattern processor's max_pattern_length
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.max_pattern_length = value
                    logger.info(f"Updated pattern_processor.max_pattern_length to {value}")
            elif key == 'stm_mode':
                processor.genome_manifest['STM_MODE'] = value
                # Update pattern processor's stm_mode
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.stm_mode = value
                    logger.info(f"Updated pattern_processor.stm_mode to {value}")
            elif key == 'persistence':
                processor.genome_manifest['PERSISTENCE'] = value
            elif key == 'recall_threshold':
                processor.genome_manifest['RECALL_THRESHOLD'] = value
            elif key == 'indexer_type':
                processor.genome_manifest['INDEXER_TYPE'] = value
            elif key == 'max_predictions':
                processor.genome_manifest['MAX_PREDICTIONS'] = value
            elif key == 'sort_symbols':
                processor.genome_manifest['SORT'] = value
            elif key == 'process_predictions':
                processor.genome_manifest['PROCESS_PREDICTIONS'] = value

    # Log session config after update
    logger.info(f"Session config after update: {session.session_config.get_config_only()}")

    # Save the updated session
    await app_state.session_manager.update_session(session)

    return {"status": "okay", "message": "Configuration updated", "session_id": session_id}


@router.post("/{session_id}/extend")
async def extend_session(session_id: str, ttl_seconds: int = 3600):
    """Extend session expiration"""
    from kato.services.kato_fastapi import app_state

    extended = await app_state.session_manager.extend_session(session_id, ttl_seconds)

    if not extended:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    return {"status": "extended", "session_id": session_id, "ttl_seconds": ttl_seconds}


@router.post("/{session_id}/observe", response_model=ObservationResult)
async def observe_in_session(
    session_id: str,
    data: ObservationData,
    request: Request
):
    """
    Process an observation in a specific session context.

    This is the core endpoint that enables multi-user support.
    Each session maintains its own isolated STM.
    """
    logger.debug(f"observe_in_session called for session: {session_id}")
    from kato.services.kato_fastapi import app_state

    # Get session lock first to ensure proper serialization
    logger.debug(f"Getting session lock for: {session_id}")
    lock = await app_state.session_manager.get_session_lock(session_id)
    logger.debug(f"Got lock result: {lock is not None} for {session_id}")
    if not lock:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    async with lock:
        # Get fresh session state inside the lock to avoid race conditions
        session = await app_state.session_manager.get_session(session_id)
        if not session:
            raise HTTPException(404, detail=f"Session {session_id} not found or expired")

        # Get node's processor (isolated per node) with session configuration
        logger.info(f"DEBUG CONCURRENT: Session node_id: {session.node_id}, session_id: {session_id}")
        logger.info(f"Getting processor for node {session.node_id} with session config: {session.session_config.get_config_only()}")
        processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)
        logger.info(f"DEBUG CONCURRENT: Got processor with ID: {processor.id}")

        # Set processor state to session's state
        logger.info(f"DEBUG: Setting processor STM to session STM: {session.stm}")
        processor.set_stm(session.stm)
        logger.info(f"DEBUG: Processor STM after setting: {processor.get_stm()}")
        processor.set_emotives_accumulator(session.emotives_accumulator)
        processor.set_metadata_accumulator(session.metadata_accumulator)
        processor.time = session.time

        # Process observation
        observation = {
            'strings': data.strings,
            'vectors': data.vectors,
            'emotives': data.emotives,
            'metadata': data.metadata,
            'unique_id': f"obs-{uuid.uuid4().hex}",
            'source': 'session'
        }

        result = await processor.observe(observation)

        # Update session state with results
        final_stm = processor.get_stm()
        logger.info(f"DEBUG: Final processor STM after observation: {final_stm}")
        session.stm = final_stm
        session.emotives_accumulator = processor.get_emotives_accumulator()
        session.metadata_accumulator = processor.get_metadata_accumulator()
        session.time = processor.time

        # Save updated session
        logger.info(f"DEBUG: Saving session with STM: {session.stm}")
        await app_state.session_manager.update_session(session)

    return ObservationResult(
        status="okay",
        session_id=session_id,
        processor_id=session.node_id,  # For v1 compatibility
        stm_length=len(session.stm),
        time=session.time,
        unique_id=result.get('unique_id', ''),
        auto_learned_pattern=result.get('auto_learned_pattern')
    )


@router.get("/{session_id}/stm", response_model=STMResponse)
async def get_session_stm(session_id: str):
    """Get the short-term memory for a specific session"""
    from kato.services.kato_fastapi import app_state

    logger.debug(f"Getting STM for session: {session_id}")

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        logger.warning(f"Session {session_id} not found")
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # If session STM is empty but processor might have state, sync from processor
    if not session.stm:
        try:
            processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)
            processor_stm = processor.get_stm()
            if processor_stm:
                logger.info(f"Session STM empty but processor has {len(processor_stm)} events, syncing to session")
                session.stm = processor_stm
                session.emotives_accumulator = processor.get_emotives_accumulator()
                session.metadata_accumulator = processor.get_metadata_accumulator()
                session.time = processor.time
                await app_state.session_manager.update_session(session)
        except Exception as sync_error:
            logger.warning(f"Failed to sync processor STM to session: {sync_error}")

    logger.debug(f"Successfully retrieved session {session_id}")
    return STMResponse(
        stm=session.stm,
        session_id=session_id,
        length=len(session.stm)
    )


@router.post("/{session_id}/learn", response_model=LearnResult)
async def learn_in_session(session_id: str):
    """Learn a pattern from the session's current STM"""
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    if not session.stm:
        raise HTTPException(400, detail="Cannot learn from empty STM")

    # Get node's processor (isolated per node) with session configuration
    processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)

    lock = await app_state.session_manager.get_session_lock(session_id)

    async with lock:
        # Set processor state
        processor.set_stm(session.stm)
        processor.set_emotives_accumulator(session.emotives_accumulator)
        processor.set_metadata_accumulator(session.metadata_accumulator)

        # Learn pattern
        pattern_name = processor.learn()

        # Update session state
        session.stm = processor.get_stm()
        session.emotives_accumulator = processor.get_emotives_accumulator()
        session.metadata_accumulator = processor.get_metadata_accumulator()

        await app_state.session_manager.update_session(session)

    return LearnResult(
        status="learned",
        pattern_name=pattern_name,
        session_id=session_id,
        message=f"Learned pattern {pattern_name} from {len(session.stm)} events"
    )


@router.post("/{session_id}/clear-stm")
async def clear_session_stm(session_id: str):
    """Clear the STM for a specific session"""
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    # Also clear the processor's STM
    processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)
    processor.clear_stm()

    cleared = await app_state.session_manager.clear_session_stm(session_id)

    if not cleared:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    return {"status": "cleared", "session_id": session_id}


@router.post("/{session_id}/clear-all")
async def clear_session_all_memory(session_id: str):
    """Clear all memory (STM and learned patterns) for a specific session"""
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    # Clear the processor's all memory (STM + learned patterns)
    processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)
    processor.clear_all_memory()

    # Clear session STM and emotives
    cleared = await app_state.session_manager.clear_session_stm(session_id)

    if not cleared:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    return {"status": "cleared", "session_id": session_id, "scope": "all"}


@router.post("/{session_id}/observe-sequence", response_model=ObservationSequenceResult)
async def observe_sequence_in_session(
    session_id: str,
    data: ObservationSequenceRequest
):
    """
    Process multiple observations in sequence within a session context.

    Provides bulk processing capabilities with options for:
    - Sequential processing with shared STM context
    - Isolated processing where each observation gets fresh STM
    - Auto-learning after each observation or at the end
    """
    from kato.api.schemas import ObservationSequenceResult
    from kato.services.kato_fastapi import app_state

    # Get session lock for thread-safe operations
    lock = await app_state.session_manager.get_session_lock(session_id)
    if not lock:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    async with lock:
        # Get fresh session state inside the lock
        session = await app_state.session_manager.get_session(session_id)
        if not session:
            raise HTTPException(404, detail=f"Session {session_id} not found or expired")

        # Handle empty batch
        if not data.observations:
            return ObservationSequenceResult(
                status="completed",
                processor_id=session.node_id,
                observations_processed=0,
                initial_stm_length=len(session.stm),
                final_stm_length=len(session.stm),
                results=[],
                auto_learned_patterns=[],
                final_learned_pattern=None,
                isolated=data.clear_stm_between
            )

        # Get processor for this session
        processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)

        # Set processor state from session
        processor.set_stm(session.stm)
        processor.set_emotives_accumulator(session.emotives_accumulator)
        processor.set_metadata_accumulator(session.metadata_accumulator)
        processor.time = session.time

        logger.info(f"Processing sequence of {len(data.observations)} observations in session {session_id}")

        results = []
        initial_stm_length = len(processor.get_stm())
        auto_learned_patterns = []

        for i, obs_data in enumerate(data.observations):
            # Clear STM before each observation if isolation requested
            if data.clear_stm_between and i > 0:
                processor.clear_stm()
                logger.debug(f"Cleared STM for isolated observation {i}")

            observation = {
                'strings': obs_data.strings,
                'vectors': obs_data.vectors,
                'emotives': obs_data.emotives,
                'metadata': obs_data.metadata,
                'unique_id': obs_data.unique_id or f"seq-obs-{uuid.uuid4().hex}",
                'source': 'sequence'
            }

            result = await processor.observe(observation)

            # Learn after each if requested
            if data.learn_after_each and processor.get_stm():
                pattern_name = processor.learn()
                auto_learned_patterns.append(pattern_name)

            # Track auto-learned patterns from auto-learning
            if result.get('auto_learned_pattern'):
                auto_learned_patterns.append(result['auto_learned_pattern'])

            observation_result = {
                "status": "okay",
                "sequence_position": i,
                "stm_length": len(processor.get_stm()),
                "time": processor.time,
                "unique_id": observation['unique_id'],
                "auto_learned_pattern": result.get('auto_learned_pattern')
            }
            results.append(observation_result)

        # Learn from final STM if requested and STM is not empty
        final_learned_pattern = None
        if data.learn_at_end:
            final_stm = processor.get_stm()
            if final_stm:
                try:
                    final_learned_pattern = processor.learn()
                    auto_learned_patterns.append(final_learned_pattern)
                    logger.info(f"Learned final pattern: {final_learned_pattern}")
                except Exception as learn_error:
                    logger.warning(f"Failed to learn final pattern: {learn_error}")

        final_stm_length = len(processor.get_stm())

        # Update session state with final processor state
        session.stm = processor.get_stm()
        session.emotives_accumulator = processor.get_emotives_accumulator()
        session.metadata_accumulator = processor.get_metadata_accumulator()
        session.time = processor.time

        # Save updated session
        await app_state.session_manager.update_session(session)

        return ObservationSequenceResult(
            status="completed",
            processor_id=session.node_id,
            observations_processed=len(data.observations),
            initial_stm_length=initial_stm_length,
            final_stm_length=final_stm_length,
            results=results,
            auto_learned_patterns=auto_learned_patterns,
            final_learned_pattern=final_learned_pattern,
            isolated=data.clear_stm_between
        )


@router.get("/{session_id}/predictions", response_model=PredictionsResponse)
async def get_session_predictions(session_id: str):
    """Get predictions based on the session's current STM"""
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # Get node's processor (isolated per node) with session configuration
    processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)

    lock = await app_state.session_manager.get_session_lock(session_id)

    async with lock:
        # Set processor state
        processor.set_stm(session.stm)

        # Get predictions
        predictions = processor.get_predictions()

        # Get future_potentials from the pattern processor if available
        future_potentials = None
        if hasattr(processor.pattern_processor, 'future_potentials'):
            future_potentials = processor.pattern_processor.future_potentials

    return PredictionsResponse(
        predictions=predictions,
        future_potentials=future_potentials,
        session_id=session_id,
        count=len(predictions)
    )
