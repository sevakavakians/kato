#!/usr/bin/env python3
"""
KATO FastAPI Service
Direct FastAPI implementation embedding a single KatoProcessor instance.
Provides simplified direct access to KATO functionality.
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kato.workers.kato_processor import KatoProcessor
from kato.config.logging_config import (
    configure_logging, get_logger, set_trace_id, get_trace_id,
    start_request_timer, get_request_duration, PerformanceTimer
)
from kato.exceptions import (
    KatoBaseException, ObservationError, PredictionError, 
    LearningError, ValidationError, ConfigurationError,
    DatabaseConnectionError, ResourceNotFoundError
)
from kato.config.settings import Settings
from kato.config.api import APIServiceConfig
from kato.v2.monitoring.metrics import get_metrics_collector, MetricsCollector
from kato.v2.errors.handlers import setup_error_handlers

# Logger will be configured after settings are loaded
logger = logging.getLogger('kato.fastapi')

# Global processor lock (processor will be stored in app.state)
processor_lock = asyncio.Lock()
startup_time = time.time()


# Pydantic Models for Request/Response validation
class ObservationData(BaseModel):
    """Input data for observations"""
    strings: List[str] = Field(default_factory=list, description="String symbols to observe")
    vectors: List[List[float]] = Field(default_factory=list, description="Vector embeddings")
    emotives: Dict[str, float] = Field(default_factory=dict, description="Emotional values")
    unique_id: Optional[str] = Field(None, description="Optional unique identifier")


class ObservationResult(BaseModel):
    """Result of an observation"""
    status: str = Field(..., description="Status of the operation")
    processor_id: str = Field(..., description="ID of the processor")
    auto_learned_pattern: Optional[str] = Field(None, description="Pattern learned if auto-learning triggered")
    time: int = Field(..., description="Processor time counter")
    unique_id: str = Field(..., description="Unique ID of the observation")


class STMResponse(BaseModel):
    """Short-term memory response"""
    stm: List[List[str]] = Field(..., description="Current short-term memory state")
    processor_id: str = Field(..., description="ID of the processor")


class LearnResult(BaseModel):
    """Result of learning operation"""
    pattern_name: str = Field(..., description="Name of the learned pattern")
    processor_id: str = Field(..., description="ID of the processor")
    message: str = Field(..., description="Human-readable message")


class PredictionsResponse(BaseModel):
    """Predictions response"""
    predictions: List[Dict] = Field(default_factory=list, description="List of predictions")
    processor_id: str = Field(..., description="ID of the processor")


class StatusResponse(BaseModel):
    """Generic status response"""
    status: str = Field(..., description="Status of the operation")
    message: str = Field(..., description="Human-readable message")
    processor_id: str = Field(..., description="ID of the processor")


class ProcessorStatus(BaseModel):
    """Processor status information"""
    status: str = Field(..., description="Health status")
    processor_id: str = Field(..., description="ID of the processor")
    processor_name: str = Field(..., description="Name of the processor")
    uptime: float = Field(..., description="Uptime in seconds")
    stm_length: int = Field(..., description="Current STM length")
    time: int = Field(..., description="Processor time counter")


class GeneUpdate(BaseModel):
    """Gene update request"""
    gene_name: str = Field(..., description="Name of the gene to update")
    gene_value: Any = Field(..., description="New value for the gene")


class ObservationSequence(BaseModel):
    """Batch of observations to process sequentially"""
    observations: List[ObservationData] = Field(..., description="List of observations to process in sequence")
    learn_after_each: bool = Field(False, description="Learn pattern after each observation")
    learn_at_end: bool = Field(False, description="Learn pattern after all observations")
    clear_stm_between: bool = Field(False, description="Clear STM between observations")


class ObservationSequenceResult(BaseModel):
    """Result of batch observation processing"""
    status: str = Field(..., description="Overall status of the operation")
    processor_id: str = Field(..., description="ID of the processor")
    observations_processed: int = Field(..., description="Number of observations processed")
    patterns_learned: List[str] = Field(default_factory=list, description="Patterns learned during processing")
    individual_results: List[ObservationResult] = Field(default_factory=list, description="Results for each observation")
    final_predictions: Optional[List[Dict]] = Field(None, description="Predictions after all observations")


class GeneUpdates(BaseModel):
    """Multiple gene updates"""
    genes: Dict[str, Any] = Field(..., description="Dictionary of gene names and values")


class PatternResponse(BaseModel):
    """Pattern data response"""
    pattern: Dict = Field(..., description="Pattern data")
    processor_id: str = Field(..., description="ID of the processor")


class ErrorResponse(BaseModel):
    """Error response format"""
    error: Dict[str, Any] = Field(..., description="Error details")
    status: int = Field(..., description="HTTP status code")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage processor lifecycle and configuration"""
    # Create fresh settings and API config at startup
    settings = Settings()  # Fresh instance reads current environment variables
    api_config = APIServiceConfig()
    
    # Configure structured logging with settings
    configure_logging(
        level=settings.logging.log_level,
        format_type=settings.logging.log_format,
        output=settings.logging.log_output
    )
    
    # Configure logger
    global logger
    logger = get_logger('kato.fastapi', settings.processor.processor_id)
    
    # Store settings in app state for global access
    app.state.settings = settings
    app.state.api_config = api_config
    
    # Startup: Initialize processor
    processor_id = settings.processor.processor_id
    processor_name = settings.processor.processor_name
    
    # Build manifest from settings
    manifest = {
        'id': processor_id,
        'name': processor_name,
        'indexer_type': settings.processing.indexer_type,
        'max_pattern_length': settings.learning.max_pattern_length,
        'persistence': settings.learning.persistence,
        'smoothness': settings.learning.smoothness,
        'auto_act_method': settings.processing.auto_act_method,
        'auto_act_threshold': settings.processing.auto_act_threshold,
        'always_update_frequencies': settings.processing.always_update_frequencies,
        'max_predictions': settings.processing.max_predictions,
        'recall_threshold': settings.learning.recall_threshold,
        'quiescence': settings.learning.quiescence,
        'search_depth': settings.processing.search_depth,
        'sort': settings.processing.sort_symbols,
        'process_predictions': settings.processing.process_predictions
    }
    
    logger.info(f"Initializing processor: {processor_id} ({processor_name})")
    
    try:
        processor = KatoProcessor(manifest, settings=settings)
        app.state.processor = processor  # Store processor in app state
        
        # Initialize v2 monitoring
        metrics_collector = get_metrics_collector()
        app.state.metrics_collector = metrics_collector
        metrics_collector.start_collection()
        
        # Setup v2 error handlers
        setup_error_handlers(app)
        
        logger.info(f"Processor {processor_id} initialized successfully with v2 monitoring")
    except Exception as e:
        logger.error(f"Failed to initialize processor: {e}")
        raise
    
    yield
    
    # Shutdown: Cleanup
    logger.info(f"Shutting down processor: {processor_id}")
    
    # Stop metrics collection
    if hasattr(app.state, 'metrics_collector'):
        await app.state.metrics_collector.stop_collection()
        del app.state.metrics_collector
    
    # Clean up app state
    if hasattr(app.state, 'processor'):
        del app.state.processor
    if hasattr(app.state, 'settings'):
        del app.state.settings
    if hasattr(app.state, 'api_config'):
        del app.state.api_config


# Create FastAPI app with lifespan management
app = FastAPI(
    title="KATO API",
    description="Knowledge Abstraction for Traceable Outcomes - FastAPI Service",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS with default settings (will use environment variables)
# The actual configuration values come from docker-compose environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will be restricted in production via env vars
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency injection helpers
from fastapi import Depends

async def get_processor(request: Request) -> KatoProcessor:
    """Dependency to get the processor from app state."""
    return request.app.state.processor

async def get_settings(request: Request) -> Settings:
    """Dependency to get settings from app state."""
    return request.app.state.settings

async def get_api_config(request: Request) -> APIServiceConfig:
    """Dependency to get API config from app state."""
    return request.app.state.api_config

async def get_metrics_collector_from_app(request: Request) -> MetricsCollector:
    """Dependency to get metrics collector from app state."""
    return request.app.state.metrics_collector

# Add request/response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log all requests and responses with trace IDs.
    """
    # Generate or extract trace ID
    trace_id = request.headers.get('X-Trace-ID') or set_trace_id()
    
    # Start request timer
    start_request_timer()
    start_time = time.time()
    
    # Log request
    logger.info(
        f"Request started: {request.method} {request.url.path}",
        extra={'extra_fields': {
            'method': request.method,
            'path': request.url.path,
            'client': request.client.host if request.client else None,
            'trace_id': trace_id
        }}
    )
    
    try:
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        duration_seconds = duration_ms / 1000.0
        
        # Record metrics if collector is available
        if hasattr(request.app.state, 'metrics_collector'):
            try:
                metrics_collector = request.app.state.metrics_collector
                metrics_collector.record_request(
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration=duration_seconds
                )
            except Exception as e:
                # Don't let metrics recording break the request
                logger.warning(f"Failed to record metrics: {e}")
        
        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code} in {duration_ms:.2f}ms",
            extra={'extra_fields': {
                'method': request.method,
                'path': request.url.path,
                'status_code': response.status_code,
                'duration_ms': round(duration_ms, 2),
                'trace_id': trace_id
            }}
        )
        
        # Add trace ID to response headers
        response.headers['X-Trace-ID'] = trace_id
        
        return response
        
    except Exception as e:
        # Calculate duration even for errors
        duration_ms = (time.time() - start_time) * 1000
        duration_seconds = duration_ms / 1000.0
        
        # Record error metrics if collector is available
        if hasattr(request.app.state, 'metrics_collector'):
            try:
                metrics_collector = request.app.state.metrics_collector
                metrics_collector.record_request(
                    path=request.url.path,
                    method=request.method,
                    status_code=500,  # Default error status
                    duration=duration_seconds
                )
            except Exception as metrics_error:
                # Don't let metrics recording break the request
                logger.warning(f"Failed to record error metrics: {metrics_error}")
        
        # Log error
        logger.error(
            f"Request failed: {request.method} {request.url.path} - {str(e)} after {duration_ms:.2f}ms",
            extra={'extra_fields': {
                'method': request.method,
                'path': request.url.path,
                'error': str(e),
                'duration_ms': round(duration_ms, 2),
                'trace_id': trace_id
            }}
        )
        
        # Re-raise the exception
        raise


# Custom exception handler for KatoBaseException
@app.exception_handler(KatoBaseException)
async def kato_exception_handler(request: Request, exc: KatoBaseException):
    """
    Handle KATO-specific exceptions with proper logging and response formatting.
    """
    # Add trace ID if not present
    if not exc.trace_id:
        exc.trace_id = get_trace_id()
    
    # Log the exception
    logger.error(
        f"KATO exception: {exc.error_code} - {exc.message}",
        extra={'extra_fields': exc.to_dict()}
    )
    
    # Return structured error response
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
        headers={'X-Trace-ID': exc.trace_id} if exc.trace_id else {}
    )


# Health and Status Endpoints
@app.get("/health")
async def health_check(
    processor: KatoProcessor = Depends(get_processor),
    settings: Settings = Depends(get_settings)
):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "processor_id": processor.id if processor else None,
        "uptime": time.time() - startup_time
    }


@app.get("/status", response_model=ProcessorStatus)
async def get_status(
    processor: KatoProcessor = Depends(get_processor),
    settings: Settings = Depends(get_settings)
):
    """Get processor status"""
    
    async with processor_lock:
        with PerformanceTimer(logger, 'get_status'):
            stm_length = len(processor.get_stm())
        
    return ProcessorStatus(
        status="okay",
        processor_id=processor.id,
        processor_name=processor.name,
        uptime=time.time() - startup_time,
        stm_length=stm_length,
        time=processor.time
    )


# Core KATO Operations
@app.post("/observe", response_model=ObservationResult)
async def observe(
    data: ObservationData,
    processor: KatoProcessor = Depends(get_processor)
):
    """Process an observation"""
    
    # Generate unique ID if not provided
    if not data.unique_id:
        data.unique_id = f"obs-{uuid.uuid4().hex}-{int(time.time() * 1000000)}"
    
    # Validate vectors if provided
    if data.vectors:
        for i, vector in enumerate(data.vectors):
            if not isinstance(vector, list) or not all(isinstance(v, (int, float)) for v in vector):
                raise ValidationError(
                    f"Invalid vector at index {i}: vectors must be lists of numbers",
                    field_name=f"vectors[{i}]",
                    field_value=str(vector)[:100],
                    trace_id=get_trace_id()
                )
    
    # Prepare observation data
    observation = {
        'strings': data.strings,
        'vectors': data.vectors,
        'emotives': data.emotives,
        'unique_id': data.unique_id,
        'source': 'fastapi'
    }
    
    # Process observation with lock to ensure sequential processing
    async with processor_lock:
        try:
            with PerformanceTimer(logger, 'observe', {'observation_id': data.unique_id}):
                result = processor.observe(observation)
            
            return ObservationResult(
                status="okay",
                processor_id=processor.id,
                auto_learned_pattern=result.get('auto_learned_pattern'),
                time=processor.time,
                unique_id=result.get('unique_id', data.unique_id)
            )
        except Exception as e:
            # Wrap unknown exceptions in ObservationError
            raise ObservationError(
                f"Failed to process observation: {str(e)}",
                observation_id=data.unique_id,
                observation_data={'strings': data.strings[:5] if data.strings else []},  # Limited preview
                trace_id=get_trace_id()
            )


@app.get("/stm", response_model=STMResponse)
@app.get("/short-term-memory", response_model=STMResponse)
async def get_stm(
    processor: KatoProcessor = Depends(get_processor)
):
    """Get current short-term memory"""
    async with processor_lock:
        stm = processor.get_stm()
    
    return STMResponse(
        stm=stm,
        processor_id=processor.id
    )


@app.post("/observe-sequence", response_model=ObservationSequenceResult)
async def observe_sequence(
    data: ObservationSequence,
    processor: KatoProcessor = Depends(get_processor)
):
    """
    Process a sequence of observations in batch.
    
    This endpoint allows efficient processing of multiple observations in a single API call.
    Each observation is processed independently with proper isolation.
    
    Options:
    - learn_after_each: Learn pattern after each individual observation
    - learn_at_end: Learn pattern once after processing all observations
    - clear_stm_between: Clear STM between observations for complete isolation
    """
    
    patterns_learned = []
    individual_results = []
    observations_processed = 0
    
    async with processor_lock:
        try:
            # Process each observation in sequence
            for idx, obs_data in enumerate(data.observations):
                # Clear STM between observations if requested
                if idx > 0 and data.clear_stm_between:
                    processor.clear_stm()
                
                # Generate unique ID if not provided
                if not obs_data.unique_id:
                    obs_data.unique_id = f"batch-obs-{idx}-{uuid.uuid4().hex}-{int(time.time() * 1000000)}"
                
                # Prepare observation data
                observation = {
                    'strings': obs_data.strings,
                    'vectors': obs_data.vectors,
                    'emotives': obs_data.emotives,
                    'unique_id': obs_data.unique_id,
                    'source': 'fastapi-batch'
                }
                
                # Process observation
                result = processor.observe(observation)
                observations_processed += 1
                
                # Create individual result
                individual_result = ObservationResult(
                    status="okay",
                    processor_id=processor.id,
                    auto_learned_pattern=result.get('auto_learned_pattern'),
                    time=processor.time,
                    unique_id=result.get('unique_id', obs_data.unique_id)
                )
                individual_results.append(individual_result)
                
                # Learn after each observation if requested
                # Note: Learning always clears STM
                if data.learn_after_each:
                    pattern_name = processor.learn()
                    if pattern_name:
                        patterns_learned.append(pattern_name)
            
            # Learn at end if requested
            # Note: Learning always clears STM, regardless of the learning mode
            if data.learn_at_end and not data.clear_stm_between:
                pattern_name = processor.learn()
                if pattern_name:
                    patterns_learned.append(pattern_name)
            
            # Get final predictions if STM has content
            final_predictions = None
            if not data.clear_stm_between or not data.learn_after_each:
                # predictions is an attribute, not a method
                final_predictions = processor.predictions
                # Rename 'name' to 'pattern_name' for consistency with API conventions
                if final_predictions:
                    for pred in final_predictions:
                        if isinstance(pred, dict) and 'name' in pred:
                            pred['pattern_name'] = pred.pop('name')
            
            return ObservationSequenceResult(
                status="okay",
                processor_id=processor.id,
                observations_processed=observations_processed,
                patterns_learned=patterns_learned,
                individual_results=individual_results,
                final_predictions=final_predictions
            )
            
        except Exception as e:
            logger.error(f"Error processing observation sequence: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn", response_model=LearnResult)
async def learn(
    processor: KatoProcessor = Depends(get_processor)
):
    """Learn from current STM"""
    
    async with processor_lock:
        try:
            pattern_name = processor.learn()
            
            if pattern_name:
                message = f"Learned pattern: {pattern_name}"
            else:
                message = "Insufficient data for learning"
            
            return LearnResult(
                pattern_name=pattern_name or "",
                processor_id=processor.id,
                message=message
            )
        except Exception as e:
            logger.error(f"Error during learning: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear-stm", response_model=StatusResponse)
@app.post("/clear-short-term-memory", response_model=StatusResponse)
async def clear_stm(
    processor: KatoProcessor = Depends(get_processor)
):
    """Clear short-term memory"""
    
    async with processor_lock:
        processor.clear_stm()
    
    return StatusResponse(
        status="okay",
        message="stm-cleared",
        processor_id=processor.id
    )


@app.post("/clear-all", response_model=StatusResponse)
@app.post("/clear-all-memory", response_model=StatusResponse)
async def clear_all_memory(
    processor: KatoProcessor = Depends(get_processor)
):
    """Clear all memory"""
    
    async with processor_lock:
        processor.clear_all_memory()
    
    return StatusResponse(
        status="okay",
        message="all-cleared",
        processor_id=processor.id
    )


@app.get("/predictions", response_model=PredictionsResponse)
@app.post("/predictions", response_model=PredictionsResponse)
async def get_predictions(
    unique_id: Optional[str] = None,
    processor: KatoProcessor = Depends(get_processor)
):
    """Get predictions"""
    
    async with processor_lock:
        if unique_id:
            predictions = processor.get_predictions({'unique_id': unique_id})
        else:
            predictions = processor.get_predictions()
    
    # Add PTRN| prefix to pattern names for consistency
    for pred in predictions:
        if isinstance(pred, dict):
            name = pred.get('name', '')
            if name and not name.startswith('PTRN|'):
                pred['name'] = f'PTRN|{name}'
    
    return PredictionsResponse(
        predictions=predictions,
        processor_id=processor.id
    )


# Advanced Operations
@app.get("/pattern/{pattern_id}", response_model=PatternResponse)
async def get_pattern(
    pattern_id: str,
    processor: KatoProcessor = Depends(get_processor)
):
    """Get pattern by ID"""
    
    async with processor_lock:
        result = processor.get_pattern(pattern_id)
    
    if result.get('status') == 'error':
        raise HTTPException(status_code=404, detail=result.get('message'))
    
    return PatternResponse(
        pattern=result.get('pattern', {}),
        processor_id=processor.id
    )


@app.post("/genes/update", response_model=StatusResponse)
async def update_genes(
    updates: GeneUpdates,
    processor: KatoProcessor = Depends(get_processor)
):
    """Update multiple gene values"""
    
    async with processor_lock:
        try:
            for gene_name, gene_value in updates.genes.items():
                # Try updating processor directly
                if hasattr(processor, gene_name):
                    setattr(processor, gene_name, gene_value)
                # Also try pattern_processor
                elif hasattr(processor.pattern_processor, gene_name):
                    setattr(processor.pattern_processor, gene_name, gene_value)
                    # Special handling for recall_threshold
                    if gene_name == 'recall_threshold' and hasattr(processor.pattern_processor, 'patterns_searcher'):
                        processor.pattern_processor.patterns_searcher.recall_threshold = gene_value
                    # Special handling for max_pattern_length - update observation_processor's copy
                    if gene_name == 'max_pattern_length' and hasattr(processor, 'observation_processor'):
                        processor.observation_processor.max_pattern_length = gene_value
                else:
                    raise ValueError(f"Unknown gene: {gene_name}")
                
                # Update genome_manifest for consistency
                if hasattr(processor, 'genome_manifest'):
                    processor.genome_manifest[gene_name] = gene_value
            
            return StatusResponse(
                status="okay",
                message="genes-updated",
                processor_id=processor.id
            )
        except Exception as e:
            logger.error(f"Error updating genes: {e}")
            raise HTTPException(status_code=400, detail=str(e))


@app.get("/gene/{gene_name}")
async def get_gene(
    gene_name: str,
    processor: KatoProcessor = Depends(get_processor)
):
    """Get gene value"""
    
    async with processor_lock:
        # Check processor first
        if hasattr(processor, gene_name):
            value = getattr(processor, gene_name)
        # Then check pattern_processor
        elif hasattr(processor.pattern_processor, gene_name):
            value = getattr(processor.pattern_processor, gene_name)
        # Finally check genome_manifest
        elif hasattr(processor, 'genome_manifest') and gene_name in processor.genome_manifest:
            value = processor.genome_manifest[gene_name]
        else:
            raise HTTPException(status_code=404, detail=f"Gene {gene_name} not found")
    
    return {
        "gene_name": gene_name,
        "gene_value": value,
        "processor_id": processor.id
    }


@app.get("/percept-data")
async def get_percept_data(
    processor: KatoProcessor = Depends(get_processor)
):
    """Get percept data"""
    
    async with processor_lock:
        data = processor.get_percept_data()
    
    return {
        "percept_data": data,
        "processor_id": processor.id
    }


@app.get("/cognition-data")
async def get_cognition_data(
    processor: KatoProcessor = Depends(get_processor)
):
    """Get cognition data"""
    
    async with processor_lock:
        data = processor.cognition_data
    
    return {
        "cognition_data": data,
        "processor_id": processor.id
    }


# WebSocket endpoint for real-time communication
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for bidirectional real-time communication"""
    # WebSockets can't use Depends the same way, get processor from app state
    if not hasattr(app.state, 'processor'):
        await websocket.close(code=1011, reason="Processor not initialized")
        return
    processor = app.state.processor
    
    await websocket.accept()
    logger.info(f"WebSocket connected for processor {processor.id}")
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            message_type = data.get('type')
            payload = data.get('payload', {})
            
            async with processor_lock:
                try:
                    if message_type == 'observe':
                        # Process observation
                        if 'unique_id' not in payload:
                            payload['unique_id'] = f"ws-{uuid.uuid4().hex}-{int(time.time() * 1000000)}"
                        payload['source'] = 'websocket'
                        
                        result = processor.observe(payload)
                        await websocket.send_json({
                            'type': 'observation_result',
                            'data': {
                                'status': 'okay',
                                'processor_id': processor.id,
                                'auto_learned_pattern': result.get('auto_learned_pattern'),
                                'time': processor.time,
                                'unique_id': result.get('unique_id')
                            }
                        })
                    
                    elif message_type == 'get_stm':
                        stm = processor.get_stm()
                        await websocket.send_json({
                            'type': 'stm',
                            'data': {
                                'stm': stm,
                                'processor_id': processor.id
                            }
                        })
                    
                    elif message_type == 'get_predictions':
                        predictions = processor.get_predictions(payload)
                        await websocket.send_json({
                            'type': 'predictions',
                            'data': {
                                'predictions': predictions,
                                'processor_id': processor.id
                            }
                        })
                    
                    elif message_type == 'learn':
                        pattern_name = processor.learn()
                        await websocket.send_json({
                            'type': 'learn_result',
                            'data': {
                                'pattern_name': pattern_name or "",
                                'processor_id': processor.id
                            }
                        })
                    
                    elif message_type == 'clear_stm':
                        processor.clear_stm()
                        await websocket.send_json({
                            'type': 'status',
                            'data': {
                                'status': 'okay',
                                'message': 'stm-cleared',
                                'processor_id': processor.id
                            }
                        })
                    
                    elif message_type == 'clear_all':
                        processor.clear_all_memory()
                        await websocket.send_json({
                            'type': 'status',
                            'data': {
                                'status': 'okay',
                                'message': 'all-cleared',
                                'processor_id': processor.id
                            }
                        })
                    
                    elif message_type == 'ping':
                        await websocket.send_json({
                            'type': 'pong',
                            'data': {
                                'processor_id': processor.id,
                                'timestamp': time.time()
                            }
                        })
                    
                    else:
                        await websocket.send_json({
                            'type': 'error',
                            'data': {
                                'message': f'Unknown message type: {message_type}'
                            }
                        })
                
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    await websocket.send_json({
                        'type': 'error',
                        'data': {
                            'message': str(e)
                        }
                    })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for processor {processor.id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))


# Error handling
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "details": {}
            },
            "status": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {
                    "error": str(exc)
                }
            },
            "status": 500
        }
    )


# Metrics endpoint
@app.get("/metrics")
async def get_metrics(
    processor: KatoProcessor = Depends(get_processor)
):
    """Get processor metrics"""
    async with processor_lock:
        stm_length = len(processor.get_stm())
        # Get pattern count from MongoDB
        try:
            pattern_count = processor.pattern_processor.superkb.patterns_kb.count_documents({})
        except:
            pattern_count = 0
    
    return {
        "processor_id": processor.id,
        "observations_processed": processor.time,
        "patterns_learned": pattern_count,
        "stm_size": stm_length,
        "uptime_seconds": time.time() - startup_time
    }


# V2 Monitoring Endpoints
@app.get("/v2/health")
async def v2_health_check(
    processor: KatoProcessor = Depends(get_processor),
    metrics_collector: MetricsCollector = Depends(get_metrics_collector_from_app)
):
    """Enhanced health check for v2 with metrics integration"""
    try:
        health_status = metrics_collector.get_health_status()
        processor_status = "healthy" if processor else "unhealthy"
        
        # Get metrics summary
        all_metrics = metrics_collector.get_all_metrics()
        metrics_collected = len(all_metrics)
        
        return {
            "status": health_status["status"],
            "processor_status": processor_status,
            "processor_id": processor.id if processor else None,
            "uptime_seconds": time.time() - startup_time,
            "issues": health_status["issues"],
            "metrics_collected": metrics_collected,
            "last_collection": health_status["timestamp"] if "timestamp" in health_status else time.time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "processor_status": "unknown",
            "processor_id": processor.id if processor else None,
            "uptime_seconds": time.time() - startup_time,
            "issues": [f"Health check error: {str(e)}"],
            "metrics_collected": 0,
            "last_collection": time.time()
        }


@app.get("/v2/metrics")
async def v2_get_comprehensive_metrics(
    processor: KatoProcessor = Depends(get_processor),
    metrics_collector: MetricsCollector = Depends(get_metrics_collector_from_app)
):
    """Get comprehensive v2 metrics including system resources and performance"""
    try:
        # Get comprehensive metrics from collector
        summary_metrics = metrics_collector.get_summary_metrics()
        rates = metrics_collector.calculate_rates()
        
        # Enhance with processor-specific data
        async with processor_lock:
            stm_length = len(processor.get_stm())
            try:
                pattern_count = processor.pattern_processor.superkb.patterns_kb.count_documents({})
            except:
                pattern_count = 0
        
        # Merge processor data into summary
        summary_metrics["processor"] = {
            "processor_id": processor.id,
            "processor_name": processor.name,
            "observations_processed": processor.time,
            "patterns_learned": pattern_count,
            "stm_size": stm_length
        }
        
        summary_metrics["rates"] = rates
        
        return summary_metrics
    except Exception as e:
        logger.error(f"Failed to get v2 metrics: {e}")
        # Return basic fallback metrics
        return {
            "error": f"Metrics collection failed: {str(e)}",
            "timestamp": time.time(),
            "processor": {
                "processor_id": processor.id if processor else None,
                "uptime_seconds": time.time() - startup_time
            }
        }


@app.get("/v2/stats")
async def v2_get_stats(
    minutes: int = 10,
    processor: KatoProcessor = Depends(get_processor),
    metrics_collector: MetricsCollector = Depends(get_metrics_collector_from_app)
):
    """Get time-series statistics for the last N minutes"""
    try:
        # Available time series metrics
        available_metrics = [
            "cpu_percent", "memory_percent", "memory_used_mb", 
            "disk_percent", "load_average_1m", "requests_total", 
            "response_time", "errors_total", "sessions_created", 
            "sessions_deleted", "session_operations",
            "mongodb_operations", "mongodb_response_time", "mongodb_errors",
            "qdrant_operations", "qdrant_response_time", "qdrant_errors",
            "redis_operations", "redis_response_time", "redis_errors"
        ]
        
        # Collect time series data for all metrics
        time_series_data = {}
        for metric_name in available_metrics:
            time_series_data[metric_name] = metrics_collector.get_time_series(metric_name, minutes)
        
        # Summary statistics
        current_status = metrics_collector.get_health_status()
        summary = metrics_collector.get_summary_metrics()
        
        return {
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "processor_id": processor.id,
            "current_status": current_status,
            "time_series": time_series_data,
            "summary": {
                "sessions": summary["sessions"],
                "performance": summary["performance"],
                "resources": summary["resources"],
                "databases": summary["databases"]
            }
        }
    except Exception as e:
        logger.error(f"Failed to get v2 stats: {e}")
        return {
            "error": f"Stats collection failed: {str(e)}",
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "processor_id": processor.id if processor else None
        }


@app.get("/v2/metrics/{metric_name}")
async def v2_get_specific_metric_history(
    metric_name: str,
    minutes: int = 10,
    metrics_collector: MetricsCollector = Depends(get_metrics_collector_from_app)
):
    """Get time series data for a specific metric"""
    try:
        time_series_data = metrics_collector.get_time_series(metric_name, minutes)
        
        if not time_series_data:
            raise HTTPException(
                status_code=404, 
                detail=f"No data available for metric '{metric_name}' in the last {minutes} minutes"
            )
        
        # Calculate basic statistics
        values = [point["value"] for point in time_series_data]
        stats = {
            "count": len(values),
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "avg": sum(values) / len(values) if values else 0
        }
        
        return {
            "metric_name": metric_name,
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "statistics": stats,
            "data_points": time_series_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metric {metric_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metric: {str(e)}")


# V2 Session Management endpoints (placeholder for future implementation)
@app.post("/v2/sessions")
async def v2_create_session():
    """Create a new v2 session (placeholder)"""
    return {
        "message": "V2 sessions not yet implemented",
        "session_id": None,
        "status": "not_implemented"
    }


if __name__ == "__main__":
    import uvicorn
    # Create fresh settings for main execution
    settings = Settings()
    api_config = APIServiceConfig()
    
    # Get uvicorn configuration
    uvicorn_config = api_config.get_uvicorn_config()
    uvicorn.run(app, **uvicorn_config)