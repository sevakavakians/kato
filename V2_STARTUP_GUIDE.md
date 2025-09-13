# KATO v2.0 Startup Guide

## Quick Start

### Option 1: Use the Startup Script (Recommended)
```bash
# This handles everything automatically
./start_v2.sh
```

The script will:
- Check if v1 is running and offer to stop it
- Build the v2.0 Docker image
- Start all v2.0 services (with Redis for sessions)
- Wait for services to be healthy
- Show you all access points

### Option 2: Manual Docker Commands
```bash
# Stop v1 if running
docker-compose down

# Build and start v2.0
docker-compose -f docker-compose.v2.yml up --build -d

# Check status
docker ps

# View logs
docker-compose -f docker-compose.v2.yml logs -f
```

## Testing v2.0

### Quick Test (Verify it's working)
```bash
python test_v2_quick.py
```

This runs a fast test to verify:
- ✅ v2.0 health endpoint is responding
- ✅ Session creation works
- ✅ Multi-user isolation is functioning
- ✅ No data collision between users

### Full Demo (See all features)
```bash
python test_v2_demo.py
```

This demonstrates:
- Multi-user session isolation
- Concurrent user support (10 users)
- Backward compatibility with v1 API
- Session-scoped learning and predictions

## Access Points

Once v2.0 is running:

### Service Endpoints
- **Primary KATO**: http://localhost:8001
- **Testing KATO**: http://localhost:8002  
- **Analytics KATO**: http://localhost:8003

### Infrastructure
- **MongoDB**: mongodb://localhost:27017
- **Qdrant**: http://localhost:6333
- **Redis**: redis://localhost:6379 (NEW in v2.0)

### API Documentation
- **OpenAPI/Swagger**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Key v2.0 Endpoints

### Session Management (NEW)
```bash
# Create a session
curl -X POST http://localhost:8001/v2/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice"}'

# Returns: {"session_id": "sess_xxxxx", "user_id": "alice", ...}
```

### Using Sessions
```bash
# Set SESSION_ID from above
SESSION_ID="sess_xxxxx"

# Observe in session (isolated STM)
curl -X POST http://localhost:8001/v2/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"]}'

# Get session STM (only this user's data)
curl http://localhost:8001/v2/sessions/$SESSION_ID/stm

# Learn from session
curl -X POST http://localhost:8001/v2/sessions/$SESSION_ID/learn

# Get predictions
curl http://localhost:8001/v2/sessions/$SESSION_ID/predictions
```

### Backward Compatibility

v1 endpoints still work:
```bash
# Without session (uses default)
curl -X POST http://localhost:8001/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["test"]}'

# With session (via header)
curl -X POST http://localhost:8001/observe \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: sess_xxxxx" \
  -d '{"strings": ["test"]}'
```

## What's Different from v1?

### 1. Docker Configuration
- **v1**: Uses `Dockerfile` and `docker-compose.yml`
- **v2**: Uses `Dockerfile.v2` and `docker-compose.v2.yml`
- **NEW**: Redis container for session storage

### 2. Service Names
- **v1**: `kato-primary`, `kato-testing`, `kato-analytics`
- **v2**: `kato-primary-v2`, `kato-testing-v2`, `kato-analytics-v2`

### 3. Database Changes
- **Write Concern**: Changed from `w=0` to `w=majority` (no data loss)
- **Session Storage**: Redis for fast session management
- **Isolation**: Each session has isolated STM state

### 4. API Changes
- **v1**: Single global STM for all users
- **v2**: Session-isolated STMs per user
- **NEW**: `/v2/sessions/*` endpoints for multi-user support

## Troubleshooting

### Problem: KeyError: 'session_id'
**Cause**: You're running v1 service, not v2
**Solution**: Use `./start_v2.sh` to start v2 services

### Problem: Connection refused on port 8001
**Cause**: Services not running
**Solution**: Run `./start_v2.sh` or `docker-compose -f docker-compose.v2.yml up -d`

### Problem: Tests show isolation failures
**Cause**: Running v1 service instead of v2
**Solution**: 
```bash
docker-compose down  # Stop v1
./start_v2.sh       # Start v2
```

### Check Service Health
```bash
# Quick health check
curl http://localhost:8001/v2/health

# Detailed status
curl http://localhost:8001/v2/status

# View logs
docker-compose -f docker-compose.v2.yml logs kato-primary-v2
```

### Reset Everything
```bash
# Stop all services
docker-compose -f docker-compose.v2.yml down

# Remove volumes (CAUTION: deletes all data)
docker-compose -f docker-compose.v2.yml down -v

# Rebuild from scratch
docker-compose -f docker-compose.v2.yml build --no-cache
docker-compose -f docker-compose.v2.yml up -d
```

## Migration from v1 to v2

### For Development
1. Stop v1: `docker-compose down`
2. Start v2: `./start_v2.sh`
3. Test: `python test_v2_quick.py`

### For Production
1. Deploy v2 alongside v1 (different ports)
2. Gradually migrate users to v2 endpoints
3. Monitor both systems
4. Deprecate v1 once migration complete

### Code Changes Required
**Minimal changes** - v1 API still works!

**Option 1**: No code changes (use v1 API)
```python
# This still works in v2
response = requests.post("http://localhost:8001/observe", 
                         json={"strings": ["test"]})
```

**Option 2**: Add session support (recommended)
```python
# Create session once
resp = requests.post("http://localhost:8001/v2/sessions",
                     json={"user_id": "user123"})
session_id = resp.json()["session_id"]

# Use session for all operations
resp = requests.post(f"http://localhost:8001/v2/sessions/{session_id}/observe",
                     json={"strings": ["test"]})
```

## Summary

KATO v2.0 is a **critical upgrade** that fixes:
- ❌ v1.0: Multiple users corrupt each other's data
- ✅ v2.0: Complete session isolation

- ❌ v1.0: Data loss with write concern 0
- ✅ v2.0: Guaranteed writes with majority concern

- ❌ v1.0: No multi-user support
- ✅ v2.0: Unlimited concurrent users

**To start using v2.0 right now:**
```bash
./start_v2.sh
python test_v2_quick.py
```

That's it! KATO v2.0 is ready for multi-user production deployment.