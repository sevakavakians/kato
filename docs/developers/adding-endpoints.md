# Adding New FastAPI Endpoints

Step-by-step guide to adding new API endpoints to KATO.

## Overview

Adding a new endpoint involves:
1. Define request/response schemas (Pydantic models)
2. Create endpoint handler function
3. Add endpoint to router
4. Write tests for the endpoint
5. Update API documentation

## Prerequisites

Before starting, ensure you understand:
- **FastAPI basics** - Routing, dependency injection, async handlers
- **Pydantic** - Request/response validation
- **KATO architecture** - Session management, KatoProcessor interface
- **Testing** - pytest fixtures, API testing patterns

## Step-by-Step Guide

### Step 1: Define Schemas

**Location**: `kato/api/schemas.py`

Define Pydantic models for request and response validation.

```python
# kato/api/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class MyNewRequest(BaseModel):
    """Request schema for new endpoint."""

    field1: str = Field(..., description="Required string field")
    field2: int = Field(default=10, ge=0, le=100, description="Optional int (0-100)")
    field3: List[str] = Field(default_factory=list, description="List of strings")

    class Config:
        json_schema_extra = {
            "example": {
                "field1": "example value",
                "field2": 42,
                "field3": ["item1", "item2"]
            }
        }

class MyNewResponse(BaseModel):
    """Response schema for new endpoint."""

    success: bool
    result: Dict[str, Any]
    message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": {"data": "processed"},
                "message": "Operation completed"
            }
        }
```

**Best Practices**:
- Use descriptive field names
- Add field descriptions for API docs
- Provide validation constraints (min, max, regex)
- Include example data for documentation
- Use `Optional[T]` for optional fields
- Use `Field(default_factory=list)` for mutable defaults

### Step 2: Create Endpoint Handler

**Location**: `kato/api/endpoints/sessions.py` (or new file)

Add endpoint handler function with proper async handling.

```python
# kato/api/endpoints/sessions.py
import logging
from fastapi import APIRouter, HTTPException, Request

from kato.api.schemas import MyNewRequest, MyNewResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger('kato.api.sessions')

@router.post("/{session_id}/my-new-endpoint", response_model=MyNewResponse)
async def my_new_endpoint(
    session_id: str,
    request: MyNewRequest
):
    """
    Description of what this endpoint does.

    Args:
        session_id: Unique session identifier
        request: Request payload with field1, field2, field3

    Returns:
        MyNewResponse with success status and result data

    Raises:
        HTTPException 404: Session not found
        HTTPException 400: Invalid input
        HTTPException 500: Internal server error
    """
    logger.info(f"my_new_endpoint called for session: {session_id}")

    try:
        # 1. Get session and processor
        from kato.services.kato_fastapi import app_state

        session = await app_state.session_manager.get_session(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        processor = session.processor

        # 2. Validate input (additional validation beyond Pydantic)
        if request.field2 > processor.config.some_threshold:
            raise HTTPException(
                status_code=400,
                detail=f"field2 exceeds threshold: {processor.config.some_threshold}"
            )

        # 3. Process request using KatoProcessor
        result = await _process_my_new_operation(
            processor,
            request.field1,
            request.field2,
            request.field3
        )

        # 4. Return response
        return MyNewResponse(
            success=True,
            result=result,
            message=f"Processed {len(request.field3)} items"
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error in my_new_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def _process_my_new_operation(
    processor,
    field1: str,
    field2: int,
    field3: List[str]
) -> Dict[str, Any]:
    """
    Helper function to process the operation.

    Separates business logic from HTTP handling.
    """
    # Implement your logic here
    # Access processor methods: processor.observe(), processor.learn(), etc.

    result = {
        "field1_processed": field1.upper(),
        "field2_multiplied": field2 * 2,
        "field3_count": len(field3),
        "stm_length": len(processor.memory_manager.stm)
    }

    return result
```

**Best Practices**:
- Use descriptive function names
- Add comprehensive docstrings
- Validate input beyond Pydantic (business rules)
- Handle errors gracefully with appropriate HTTP status codes
- Use helper functions to separate HTTP handling from business logic
- Log important operations and errors
- Use async/await for I/O operations

### Step 3: Register Endpoint

**If adding to existing router** (`sessions.py`):
- Endpoint is automatically registered when defined with `@router` decorator

**If creating new router file**:

```python
# kato/api/endpoints/my_new_module.py
from fastapi import APIRouter

router = APIRouter(prefix="/my-module", tags=["my-module"])

@router.get("/")
async def my_module_root():
    return {"message": "My new module"}

@router.post("/action")
async def my_module_action():
    return {"result": "action performed"}
```

**Register in main app** (`kato/api/main.py`):
```python
# kato/api/main.py
from kato.api.endpoints import sessions, kato_ops, my_new_module

app = FastAPI(title="KATO API", version="3.0")

# Register routers
app.include_router(sessions.router)
app.include_router(kato_ops.router)
app.include_router(my_new_module.router)  # Add new router
```

### Step 4: Write Tests

**Location**: `tests/tests/api/test_my_new_endpoint.py`

Create comprehensive tests for the new endpoint.

```python
# tests/tests/api/test_my_new_endpoint.py
import pytest
from tests.fixtures.kato_fixtures import kato_fixture

def test_my_new_endpoint_success(kato_fixture):
    """Test successful endpoint execution."""
    # Setup
    kato_fixture.clear_all_memory()

    # Add some data to STM
    kato_fixture.observe({
        'strings': ['test'],
        'vectors': [],
        'emotives': {}
    })

    # Call new endpoint
    response = kato_fixture.client.post(
        f"/sessions/{kato_fixture.session_id}/my-new-endpoint",
        json={
            "field1": "example",
            "field2": 42,
            "field3": ["item1", "item2", "item3"]
        }
    )

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['result']['field1_processed'] == "EXAMPLE"
    assert data['result']['field2_multiplied'] == 84
    assert data['result']['field3_count'] == 3
    assert data['result']['stm_length'] == 1

def test_my_new_endpoint_validation_error(kato_fixture):
    """Test endpoint with invalid input."""
    response = kato_fixture.client.post(
        f"/sessions/{kato_fixture.session_id}/my-new-endpoint",
        json={
            "field1": "example",
            "field2": 150,  # Exceeds max (100)
            "field3": []
        }
    )

    # Should return validation error
    assert response.status_code == 422

def test_my_new_endpoint_session_not_found(kato_fixture):
    """Test endpoint with non-existent session."""
    response = kato_fixture.client.post(
        "/sessions/nonexistent_session/my-new-endpoint",
        json={
            "field1": "example",
            "field2": 42,
            "field3": []
        }
    )

    assert response.status_code == 404
    assert "Session not found" in response.json()['detail']

def test_my_new_endpoint_missing_fields(kato_fixture):
    """Test endpoint with missing required fields."""
    response = kato_fixture.client.post(
        f"/sessions/{kato_fixture.session_id}/my-new-endpoint",
        json={
            "field2": 42
            # Missing required field1
        }
    )

    assert response.status_code == 422
    error = response.json()
    assert "field1" in str(error)

def test_my_new_endpoint_edge_cases(kato_fixture):
    """Test endpoint with edge case inputs."""
    # Empty list
    response = kato_fixture.client.post(
        f"/sessions/{kato_fixture.session_id}/my-new-endpoint",
        json={
            "field1": "",
            "field2": 0,
            "field3": []
        }
    )
    assert response.status_code == 200

    # Maximum values
    response = kato_fixture.client.post(
        f"/sessions/{kato_fixture.session_id}/my-new-endpoint",
        json={
            "field1": "x" * 1000,
            "field2": 100,
            "field3": ["item"] * 100
        }
    )
    assert response.status_code == 200
```

**Run Tests**:
```bash
# Start services
./start.sh

# Run tests
./run_tests.sh --no-start --no-stop tests/tests/api/test_my_new_endpoint.py -v
```

**Best Practices**:
- Test success cases
- Test validation errors (400, 422)
- Test not found errors (404)
- Test edge cases (empty inputs, max values)
- Test error handling (500)
- Use descriptive test names
- Keep tests independent and isolated

### Step 5: Update Documentation

**API Documentation** (auto-generated):
- FastAPI automatically generates OpenAPI docs from your code
- Access at `http://localhost:8000/docs`
- Ensure your endpoint has good docstrings and schema examples

**Manual Documentation** (if needed):

**Location**: `docs/reference/api/my-new-endpoint.md`

```markdown
# My New Endpoint

## Overview

Description of what this endpoint does and when to use it.

## Endpoint

```
POST /sessions/{session_id}/my-new-endpoint
```

## Request

### Parameters

- `session_id` (path): Session identifier

### Body

```json
{
  "field1": "string (required)",
  "field2": 42,
  "field3": ["item1", "item2"]
}
```

## Response

### Success (200)

```json
{
  "success": true,
  "result": {
    "field1_processed": "STRING",
    "field2_multiplied": 84,
    "field3_count": 2,
    "stm_length": 1
  },
  "message": "Processed 2 items"
}
```

### Errors

- **404**: Session not found
- **400**: Invalid input (field2 exceeds threshold)
- **422**: Validation error
- **500**: Internal server error

## Example Usage

### cURL

```bash
curl -X POST http://localhost:8000/sessions/abc123/my-new-endpoint \
  -H "Content-Type: application/json" \
  -d '{
    "field1": "example",
    "field2": 42,
    "field3": ["item1", "item2"]
  }'
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/sessions/abc123/my-new-endpoint",
    json={
        "field1": "example",
        "field2": 42,
        "field3": ["item1", "item2"]
    }
)

print(response.json())
```

## Related Endpoints

- [Observe](observe.md)
- [Learn](learn.md)
- [Predictions](predictions.md)
```

## Common Patterns

### Pattern 1: Session-Scoped Operation

Most KATO endpoints operate on a specific session:

```python
@router.post("/{session_id}/operation")
async def operation(session_id: str, request: RequestModel):
    session = await app_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    processor = session.processor
    result = processor.some_method()
    return ResponseModel(result=result)
```

### Pattern 2: Global Operation (No Session)

Some endpoints don't require a session:

```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "3.0"
    }
```

### Pattern 3: Async Processing

For long-running operations, use background tasks:

```python
from fastapi import BackgroundTasks

@router.post("/{session_id}/batch-learn")
async def batch_learn(
    session_id: str,
    background_tasks: BackgroundTasks
):
    session = await app_state.session_manager.get_session(session_id)

    # Add task to background
    background_tasks.add_task(
        _process_batch_learning,
        session.processor
    )

    return {"message": "Batch learning started"}

async def _process_batch_learning(processor):
    """Background task for batch learning."""
    for i in range(100):
        processor.learn()
```

### Pattern 4: Streaming Response

For large responses, use streaming:

```python
from fastapi.responses import StreamingResponse
import json

@router.get("/{session_id}/stream-patterns")
async def stream_patterns(session_id: str):
    """Stream patterns as JSON lines."""

    async def generate():
        patterns = await get_all_patterns(session_id)
        for pattern in patterns:
            yield json.dumps(pattern.to_dict()) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson"
    )
```

### Pattern 5: File Upload

For file-based endpoints:

```python
from fastapi import File, UploadFile

@router.post("/{session_id}/upload-observations")
async def upload_observations(
    session_id: str,
    file: UploadFile = File(...)
):
    """Upload observations from CSV file."""
    contents = await file.read()

    # Process file
    import csv
    import io
    reader = csv.DictReader(io.StringIO(contents.decode()))

    session = await app_state.session_manager.get_session(session_id)
    processor = session.processor

    count = 0
    for row in reader:
        processor.observe({
            'strings': row['strings'].split(','),
            'vectors': [],
            'emotives': {}
        })
        count += 1

    return {"uploaded": count}
```

## Debugging Endpoints

### Enable Request Logging

```python
# kato/api/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info(f"Request: {request.method} {request.url}")
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response

# Add to app
app.add_middleware(RequestLoggingMiddleware)
```

### Test Endpoint Manually

```bash
# Using curl
curl -X POST http://localhost:8000/sessions/test/my-new-endpoint \
  -H "Content-Type: application/json" \
  -d '{"field1": "test", "field2": 10, "field3": []}' \
  | jq

# Using httpie (cleaner syntax)
http POST localhost:8000/sessions/test/my-new-endpoint \
  field1=test field2:=10 field3:='[]'
```

### Interactive API Testing

```bash
# Open Swagger UI
open http://localhost:8000/docs

# Or ReDoc
open http://localhost:8000/redoc
```

## Checklist

Before committing your new endpoint:

- [ ] Pydantic schemas defined with validation
- [ ] Endpoint handler implemented with error handling
- [ ] Router registered in main app
- [ ] Tests written (success, errors, edge cases)
- [ ] All tests passing
- [ ] API documentation updated (if needed)
- [ ] Code follows KATO style guide
- [ ] Logging added for important operations
- [ ] Type hints on all functions
- [ ] Docstrings on endpoint and helper functions

## Related Documentation

- [Architecture Overview](architecture.md)
- [Testing Guide](testing.md)
- [API Reference](../reference/api/)
- [Code Organization](code-organization.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
