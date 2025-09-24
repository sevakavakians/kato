# KATO Dynamic Ports Guide

## Overview
KATO now supports dynamic port allocation to avoid port conflicts when running multiple instances or when ports are already in use by other services.

## How It Works

### 1. Internal Communication
Services communicate internally using container names on the Docker network:
- MongoDB: `mongodb://mongodb:27017`
- Qdrant: `qdrant:6333`
- Redis: `redis://redis:6379`

### 2. External Access
External ports are dynamically assigned by Docker and can be discovered using the provided tools.

## Usage

### Starting Services with Dynamic Ports

```bash
# Using docker-compose directly
docker-compose -f docker-compose.v2.dynamic.yml up -d

# Discover assigned ports
./discover-ports.sh
```

### Port Discovery

The `discover-ports.sh` script provides several commands:

```bash
# Discover and save current ports
./discover-ports.sh discover

# Show saved port mappings
./discover-ports.sh show

# Export as environment variables
source <(./discover-ports.sh export)

# Get raw JSON output
./discover-ports.sh json
```

### Example Output

```
✓ primary KATO: http://localhost:63204
✓ testing KATO: http://localhost:63205
✓ analytics KATO: http://localhost:63206
✓ MongoDB: mongodb://localhost:63203
✓ Qdrant: http://localhost:63202
✓ Redis: redis://localhost:63201
```

## Test Integration

Tests automatically discover dynamic ports:

1. First checks `.kato-ports.json` file
2. Falls back to Docker API discovery
3. Finally tries fixed ports (8001, 8002, 8003)

```python
# Tests will automatically find the right port
./run_tests.sh --no-start --no-stop
```

## Port Mappings File

Port mappings are saved to `.kato-ports.json`:

```json
{
  "timestamp": "2025-09-15T21:19:00Z",
  "services": {
    "primary": {
      "container": "kato-primary-v2",
      "port": 63204,
      "url": "http://localhost:63204"
    },
    ...
  },
  "databases": {
    "mongodb": {
      "container": "kato-mongodb-v2",
      "port": 63203,
      "url": "mongodb://localhost:63203"
    },
    ...
  }
}
```

## Benefits

1. **No Port Conflicts**: Multiple KATO environments can run simultaneously
2. **Flexible Deployment**: Works in any environment without port configuration
3. **Automatic Discovery**: Tests and scripts automatically find the right ports
4. **Backward Compatible**: Falls back to fixed ports if needed

## Switching Between Fixed and Dynamic Ports

### Use Fixed Ports (Original)
```bash
docker-compose -f docker-compose.v2.yml up -d
```

### Use Dynamic Ports
```bash
docker-compose -f docker-compose.v2.dynamic.yml up -d
./discover-ports.sh
```

## Environment Variables

After discovery, you can export ports as environment variables:

```bash
source <(./discover-ports.sh export)

# Available variables:
echo $KATO_PRIMARY_URL    # http://localhost:63204
echo $KATO_TESTING_URL    # http://localhost:63205
echo $MONGODB_URL         # mongodb://localhost:63203
```

## Troubleshooting

### Services Not Found
If port discovery fails:
1. Ensure containers are running: `docker ps`
2. Re-run discovery: `./discover-ports.sh discover`
3. Check container logs: `docker logs kato-primary-v2`

### Tests Can't Find Services
1. Run discovery after starting services
2. Ensure `.kato-ports.json` exists
3. Tests will automatically fall back to fixed ports

### Port Already in Use
This is exactly what dynamic ports solve! Use `docker-compose.v2.dynamic.yml` instead of the fixed port version.