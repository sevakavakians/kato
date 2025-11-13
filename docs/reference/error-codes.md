# Error Codes Reference

HTTP status codes and error responses in KATO API.

## HTTP Status Codes

### 2xx Success

| Code | Status | Usage |
|------|--------|-------|
| 200 | OK | Successful GET, POST, or operation |
| 201 | Created | Resource created successfully |

### 4xx Client Errors

| Code | Status | Common Causes |
|------|--------|---------------|
| 400 | Bad Request | Invalid request data, vector dimension mismatch, empty STM |
| 404 | Not Found | Session expired/not found, pattern not found |

### 5xx Server Errors

| Code | Status | Common Causes |
|------|--------|---------------|
| 500 | Internal Server Error | Unexpected server error, database connection issues |
| 503 | Service Unavailable | Service temporarily unavailable, overload |

## Error Response Format

### Standard Error

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Vector Dimension Error (400)

```json
{
  "detail": {
    "error": "VectorDimensionError",
    "message": "Vector dimension mismatch",
    "expected_dimension": 768,
    "actual_dimension": 512,
    "vector_name": "VCTR|abc123..."
  }
}
```

### Session Not Found (404)

```json
{
  "detail": "Session session-abc123... not found or expired"
}
```

## Common Errors

### Session Expired

**Code**: 404

**Cause**: Session TTL expired or manually deleted

**Response**:

```json
{
  "detail": "Session {session_id} not found or expired"
}
```

**Solution**: Create a new session

### Empty STM

**Code**: 400

**Cause**: Attempting to learn from empty STM

**Response**:

```json
{
  "detail": "Cannot learn from empty STM"
}
```

**Solution**: Process observations first

### Vector Dimension Mismatch

**Code**: 400

**Cause**: Vector not 768 dimensions

**Response**:

```json
{
  "detail": {
    "error": "VectorDimensionError",
    "message": "Vector dimension mismatch",
    "expected_dimension": 768,
    "actual_dimension": 512
  }
}
```

**Solution**: Use 768-dimensional embeddings

### Pattern Not Found

**Code**: 404

**Cause**: Pattern ID doesn't exist

**Response**:

```json
{
  "detail": "Pattern PTRN|abc123... not found"
}
```

**Solution**: Verify pattern ID

### Configuration Validation Error

**Code**: 400

**Cause**: Invalid configuration parameter

**Response**:

```json
{
  "detail": "Invalid recall_threshold: 1.5 (must be 0.0-1.0)"
}
```

**Solution**: Use valid parameter values

## Error Handling Examples

### Python

```python
import requests

try:
    response = requests.post(
        f"http://localhost:8000/sessions/{session_id}/observe",
        json={"strings": ["hello"]}
    )
    response.raise_for_status()
    data = response.json()
except requests.HTTPError as e:
    if e.response.status_code == 404:
        # Session expired - create new one
        session = create_session()
    elif e.response.status_code == 400:
        error = e.response.json()
        if isinstance(error.get("detail"), dict):
            # Structured error (e.g., VectorDimensionError)
            print(f"Error: {error['detail']['error']}")
            print(f"Message: {error['detail']['message']}")
        else:
            # Simple error
            print(f"Bad request: {error['detail']}")
    else:
        # Other error
        raise
```

### JavaScript

```javascript
try {
  const response = await fetch(
    `http://localhost:8000/sessions/${sessionId}/observe`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({strings: ['hello']})
    }
  );

  if (!response.ok) {
    const error = await response.json();

    if (response.status === 404) {
      // Session expired
      const newSession = await createSession();
      return retryObserve(newSession.session_id);
    } else if (response.status === 400) {
      // Bad request
      console.error('Bad request:', error.detail);
    } else {
      // Other error
      throw new Error(error.detail);
    }
  }

  return await response.json();
} catch (error) {
  console.error('Request failed:', error);
  throw error;
}
```

## See Also

- [API Reference](api/README.md) - Complete API documentation
- [Troubleshooting](../users/troubleshooting.md) - Common issues and solutions

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
