"""
Session Management Endpoints

Handles session creation, management, and session-scoped KATO operations.
"""

import asyncio
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
    from kato.config.configuration_service import get_configuration_service

    logger.info(f"Creating session with manager id: {id(app_state.session_manager)}")
    logger.debug(f"Calling session_manager.create_session for node: {request.node_id}")
    session = await app_state.session_manager.create_session(
        node_id=request.node_id,
        config=request.config,
        metadata=request.metadata,
        ttl_seconds=request.ttl_seconds
    )
    logger.debug(f"Session created: {session.session_id}")

    # Get effective config (merges session config with system defaults)
    config_service = get_configuration_service()
    defaults = config_service.get_default_configuration()
    effective_config = session.session_config.get_effective_config(defaults) if hasattr(session, 'session_config') else {}

    return SessionResponse(
        session_id=session.session_id,
        node_id=session.node_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        ttl_seconds=request.ttl_seconds or 3600,  # Use provided TTL or default
        metadata=session.metadata,
        session_config=effective_config
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


@router.get("/{session_id}/exists")
async def check_session_exists(session_id: str):
    """
    Check if session exists without extending its TTL.

    This endpoint is useful for testing expiration behavior since
    it won't trigger auto-extension when SESSION_AUTO_EXTEND is enabled.

    Returns:
        exists: Whether session exists in Redis
        expired: Whether session has expired (if exists)
    """
    from kato.services.kato_fastapi import app_state

    # Check Redis directly first to avoid auto-deletion of expired sessions
    if hasattr(app_state.session_manager, 'redis_client'):
        if not app_state.session_manager._connected:
            await app_state.session_manager.initialize()

        key = f"{app_state.session_manager.key_prefix}{session_id}"
        exists = await app_state.session_manager.redis_client.exists(key)

        if not exists:
            return {
                "exists": False,
                "expired": False,
                "session_id": session_id
            }

        # Session exists in Redis, check if it's expired
        session = await app_state.session_manager.get_session(session_id, check_only=True)
        if not session:
            # Exists but get_session returned None = expired (and now deleted)
            return {
                "exists": False,  # Was deleted
                "expired": True,  # But it was expired
                "session_id": session_id
            }

        # Session exists and is valid
        return {
            "exists": True,
            "expired": False,
            "session_id": session_id
        }

    # Fallback for non-Redis session manager
    session = await app_state.session_manager.get_session(session_id, check_only=True)
    return {
        "exists": session is not None,
        "expired": False if session else False,
        "session_id": session_id
    }


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_info(session_id: str):
    """Get information about a session"""
    from kato.services.kato_fastapi import app_state
    from kato.config.configuration_service import get_configuration_service

    logger.info(f"Getting session info for: {session_id}")
    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # Calculate TTL from expires_at - current time
    ttl_seconds = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())

    # Get effective config (merges session config with system defaults)
    config_service = get_configuration_service()
    defaults = config_service.get_default_configuration()
    effective_config = session.session_config.get_effective_config(defaults) if hasattr(session, 'session_config') else {}

    return SessionResponse(
        session_id=session.session_id,
        node_id=session.node_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        ttl_seconds=max(0, ttl_seconds),  # Ensure non-negative
        metadata=session.metadata,
        session_config=effective_config
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    from kato.services.kato_fastapi import app_state

    deleted = await app_state.session_manager.delete_session(session_id)

    if not deleted:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    return {"status": "deleted", "session_id": session_id}


@router.get("/{session_id}/config")
async def get_session_config(session_id: str):
    """
    Get effective configuration for a session.

    Returns all configurable parameters with their effective values
    (session overrides or system defaults).
    """
    from kato.services.kato_fastapi import app_state
    from kato.config.configuration_service import get_configuration_service

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # Get configuration service
    config_service = get_configuration_service()

    # Get defaults
    defaults = config_service.get_default_configuration()

    # Get effective config (merges session config with defaults)
    effective_config = session.session_config.get_effective_config(defaults)

    return {
        "session_id": session_id,
        "config": effective_config
    }


@router.post("/{session_id}/config")
async def update_session_config(session_id: str, request_data: dict[str, Any]):
    """Update session configuration parameters"""
    from kato.services.kato_fastapi import app_state
    from kato.config.configuration_service import get_configuration_service

    logger.error(f"!!! DEBUG: update_session_config called for {session_id} with: {request_data}")
    logger.info(f"Updating config for session {session_id} with data: {request_data}")

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found")

    # Extract config from request - it comes as {"config": {...}}
    config = request_data.get('config', request_data)
    logger.info(f"Extracted config: {config}")

    # Validate configuration using ConfigurationService
    config_service = get_configuration_service()
    validation_errors = config_service.validate_configuration_update(config)

    if validation_errors:
        logger.error(f"Configuration validation failed: {validation_errors}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Configuration validation failed",
                "validation_errors": validation_errors
            }
        )

    # AUTO-TOGGLE SORT based on use_token_matching if provided
    if 'use_token_matching' in config and 'sort_symbols' not in config:
        # Auto-set sort_symbols based on use_token_matching
        config['sort_symbols'] = config['use_token_matching']
        logger.info(f"Auto-toggled sort_symbols={config['sort_symbols']} based on use_token_matching={config['use_token_matching']}")
    elif 'use_token_matching' in config and 'sort_symbols' in config:
        # Warn if there's a mismatch
        if config['sort_symbols'] != config['use_token_matching']:
            logger.warning(
                f"CONFIGURATION MISMATCH: sort_symbols={config['sort_symbols']} with use_token_matching={config['use_token_matching']}. "
                f"Token-level matching requires sort_symbols=True, character-level requires sort_symbols=False. "
                f"Using user-specified values, but this may cause incorrect matching behavior."
            )

    # Update the session's config - using SessionConfiguration's update method
    for key, value in config.items():
        if hasattr(session.session_config, key):
            setattr(session.session_config, key, value)
            logger.info(f"Updated session config {key} = {value}")
        else:
            logger.warning(f"Session config does not have attribute {key}")

    # Save the updated session to Redis
    logger.info("Saving updated session to Redis")
    await app_state.session_manager.update_session(session)
    logger.info(f"Session saved successfully with config: {session.session_config.get_config_only()}")

    # Note: Processors are stateless and receive config as parameters.
    # The updated config will be used on the next observe/prediction call.
    # No need to update existing processor instances.

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

        # Process observation - NO PROCESSOR LOCK NEEDED (stateless processor)
        # Processor accepts session state as parameter and returns new state
        observation = {
            'strings': data.strings,
            'vectors': data.vectors,
            'emotives': data.emotives,
            'metadata': data.metadata,
            'unique_id': f"obs-{uuid.uuid4().hex}",
            'source': 'session'
        }

        try:
            # Call stateless observe() - pass session state, get new state back
            result = await processor.observe(
                observation,
                session_state=session,
                config=session.session_config
            )
        except Exception as e:
            # Import VectorDimensionError to check exception type
            from kato.exceptions import VectorDimensionError

            # Check if this is a vector dimension error
            if isinstance(e, VectorDimensionError):
                logger.error(f"Vector dimension error in session {session_id}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "VectorDimensionError",
                        "message": str(e),
                        "expected_dimension": e.context.get('expected_dimension'),
                        "actual_dimension": e.context.get('actual_dimension'),
                        "vector_name": e.context.get('vector_name')
                    }
                )
            # Re-raise other exceptions
            raise

        # Update session with new state returned by processor
        logger.info(f"DEBUG: Updating session with new state from processor")
        session.stm = result['stm']
        session.emotives_accumulator = result['emotives_accumulator']
        session.metadata_accumulator = result['metadata_accumulator']
        session.time = result['time']
        session.percept_data = result['percept_data']
        session.predictions = result.get('predictions', [])

        # Save updated session (outside processor lock but inside session lock)
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

    # NOTE: With stateless processors, session is the source of truth
    # No need to sync from processor (processor doesn't hold state)

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
        # NO PROCESSOR LOCK NEEDED (stateless processor)
        # Learn pattern - stateless call returns (pattern_name, new_stm)
        pattern_name, new_stm = processor.learn(session_state=session)

        # Update session state
        session.stm = new_stm

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

    # NOTE: With stateless processors, just clear session STM in Redis
    # No need to clear processor STM (processor doesn't hold state)
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
    # NO LOCK NEEDED - clear_all_memory is a database side-effect operation (clears LTM)
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

    # Background heartbeat task to keep session alive during long operations
    async def _session_heartbeat(interval_seconds: int = 30):
        """
        Periodically extend session TTL during long-running operations.

        This ensures sessions don't expire mid-processing, even if the operation
        takes longer than the client timeout or session TTL.
        """
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                session = await app_state.session_manager.get_session(session_id)
                if session:
                    # get_session() with auto_extend=True already extends and saves the session
                    logger.debug(f"Heartbeat: extended session {session_id}")
                else:
                    logger.warning(f"Heartbeat: session {session_id} no longer exists")
                    break
        except asyncio.CancelledError:
            logger.debug(f"Heartbeat cancelled for session {session_id}")
            raise

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

        # NO PROCESSOR LOCK NEEDED (stateless processor)
        # Process entire sequence with stateless state chaining
        logger.info(f"Processing sequence of {len(data.observations)} observations in session {session_id}")

        # Start heartbeat for large batches to prevent session expiration during long operations
        heartbeat_task = None
        if len(data.observations) > 50:  # Start heartbeat for batches >50 observations
            heartbeat_task = asyncio.create_task(_session_heartbeat(interval_seconds=30))
            logger.debug(f"Started session heartbeat for {len(data.observations)} observations")

        results = []
        initial_stm_length = len(session.stm)
        auto_learned_patterns = []

        # Track current session state through sequence (stateless approach)
        current_state = session

        try:
            for i, obs_data in enumerate(data.observations):
                # Clear STM before each observation if isolation requested
                if data.clear_stm_between and i > 0:
                    from kato.workers.memory_manager import MemoryManager
                    current_state.stm = MemoryManager.clear_symbols()
                    logger.debug(f"Cleared STM for isolated observation {i}")

                observation = {
                    'strings': obs_data.strings,
                    'vectors': obs_data.vectors,
                    'emotives': obs_data.emotives,
                    'metadata': obs_data.metadata,
                    'unique_id': obs_data.unique_id or f"seq-obs-{uuid.uuid4().hex}",
                    'source': 'sequence'
                }

                try:
                    # Stateless observe() - pass current state, get new state back
                    result = await processor.observe(
                        observation,
                        session_state=current_state,
                        config=session.session_config
                    )
                except Exception as e:
                    # Import VectorDimensionError to check exception type
                    from kato.exceptions import VectorDimensionError

                    # Cancel heartbeat before raising
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

                    # Check if this is a vector dimension error
                    if isinstance(e, VectorDimensionError):
                        logger.error(f"Vector dimension error at observation {i} in session {session_id}: {e}")
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "VectorDimensionError",
                                "message": str(e),
                                "observation_index": i,
                                "expected_dimension": e.context.get('expected_dimension'),
                                "actual_dimension": e.context.get('actual_dimension'),
                                "vector_name": e.context.get('vector_name')
                            }
                        )
                    # Re-raise other exceptions
                    raise

                # Update current state with result (stateless chaining)
                current_state.stm = result['stm']
                current_state.time = result['time']
                current_state.emotives_accumulator = result['emotives_accumulator']
                current_state.metadata_accumulator = result['metadata_accumulator']
                current_state.percept_data = result['percept_data']
                current_state.predictions = result.get('predictions', [])

                # Learn after each if requested
                if data.learn_after_each and current_state.stm:
                    pattern_name, new_stm = processor.learn(session_state=current_state)
                    current_state.stm = new_stm
                    auto_learned_patterns.append(pattern_name)

                # Track auto-learned patterns from auto-learning
                if result.get('auto_learned_pattern'):
                    auto_learned_patterns.append(result['auto_learned_pattern'])

                observation_result = {
                    "status": "okay",
                    "sequence_position": i,
                    "stm_length": len(current_state.stm),
                    "time": current_state.time,
                    "unique_id": observation['unique_id'],
                    "auto_learned_pattern": result.get('auto_learned_pattern')
                }
                results.append(observation_result)

            # Learn from final STM if requested and STM is not empty
            final_learned_pattern = None
            if data.learn_at_end and current_state.stm:
                try:
                    final_learned_pattern, new_stm = processor.learn(session_state=current_state)
                    current_state.stm = new_stm
                    auto_learned_patterns.append(final_learned_pattern)
                    logger.info(f"Learned final pattern: {final_learned_pattern}")
                except Exception as learn_error:
                    logger.warning(f"Failed to learn final pattern: {learn_error}")

            final_stm_length = len(current_state.stm)

        finally:
            # Always cancel the heartbeat task if it was started
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                logger.debug(f"Cancelled heartbeat for session {session_id}")

        # Update session with final state (current_state has all updates from sequence)
        session.stm = current_state.stm
        session.emotives_accumulator = current_state.emotives_accumulator
        session.metadata_accumulator = current_state.metadata_accumulator
        session.time = current_state.time
        session.percept_data = current_state.percept_data
        session.predictions = current_state.predictions

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
        # NO PROCESSOR LOCK NEEDED (stateless processor)
        # Get predictions with session state - stateless call
        predictions = await processor.get_predictions(
            session_state=session,
            config=session.session_config
        )

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


@router.get("/{session_id}/percept-data")
async def get_session_percept_data(session_id: str):
    """
    Get percept data (input observation data) for a specific session.

    Returns the most recent observation data sent to this session via
    observe or observe_sequence calls. This data is session-isolated.

    Args:
        session_id: Session identifier

    Returns:
        Percept data and session metadata
    """
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    return {
        "percept_data": session.percept_data,
        "session_id": session_id,
        "node_id": session.node_id
    }


@router.get("/{session_id}/cognition-data")
async def get_session_cognition_data(session_id: str):
    """
    Get cognition data (processing outputs) for a specific session.

    Returns predictions and other cognitive processing results from this session.
    This data is session-isolated and reflects the session's most recent state.

    Args:
        session_id: Session identifier

    Returns:
        Cognition data including predictions, emotives, and symbols
    """
    from kato.services.kato_fastapi import app_state

    session = await app_state.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")

    # Get processor to access current symbols
    processor = await app_state.processor_manager.get_processor(session.node_id, session.session_config)

    # Set processor state to session's state to get accurate symbols
    processor.set_stm(session.stm)

    return {
        "cognition_data": {
            "predictions": session.predictions,
            "emotives": session.emotives_accumulator,
            "symbols": processor.memory_manager.symbols,
            "time": session.time
        },
        "session_id": session_id,
        "node_id": session.node_id
    }
