# KATO Dynamic Ports Update

## What Changed

KATO now uses **dynamic ports by default** to prevent port conflicts and enable multiple simultaneous environments.

## Key Changes

### 1. Default Behavior
- **OLD**: Fixed ports (8001, 8002, 8003) by default
- **NEW**: Dynamic ports assigned by Docker, discovered automatically

### 2. Using Fixed Ports
If you need the old behavior with fixed ports:
```bash
./kato-manager.sh start --fixed-ports
# or
./kato-manager.sh start -f
```

### 3. Port Discovery
After starting with dynamic ports:
```bash
# Automatic discovery happens during start
./kato-manager.sh start

# Manual discovery if needed
./discover-ports.sh

# Show saved ports
./discover-ports.sh show
```

### 4. Test Integration
Tests automatically discover dynamic ports via:
1. `.kato-ports.json` file (created by discover-ports.sh)
2. Docker API fallback
3. Fixed ports as last resort

## Benefits

1. **No Port Conflicts**: Run v1 and v2 simultaneously
2. **Multiple Environments**: Run multiple KATO instances
3. **CI/CD Friendly**: No hardcoded port dependencies
4. **Backward Compatible**: Use `--fixed-ports` for old behavior

## Quick Reference

```bash
# Start with dynamic ports (DEFAULT)
./kato-manager.sh start

# Start with fixed ports (8001-8003)
./kato-manager.sh start --fixed-ports

# Check which ports are being used
./kato-manager.sh status

# Discover ports manually
./discover-ports.sh

# Export ports as environment variables
source <(./discover-ports.sh export)
echo $KATO_PRIMARY_URL
```

## Files Changed

- `kato-manager.sh` - Now defaults to dynamic ports, added `--fixed-ports` flag
- `docker-compose.v2.dynamic.yml` - New compose file with dynamic port mappings
- `discover-ports.sh` - Port discovery and management script
- `tests/tests/fixtures/kato_fixtures.py` - Updated to auto-discover dynamic ports
- `.kato-ports.json` - Generated file with current port mappings (git-ignored)

## Migration Notes

Existing scripts/workflows will continue to work but should be updated:

### Old Way
```bash
./kato-manager.sh start
curl http://localhost:8001/health
```

### New Way (Recommended)
```bash
./kato-manager.sh start
source <(./discover-ports.sh export)
curl $KATO_PRIMARY_URL/health
```

### Keep Old Behavior
```bash
./kato-manager.sh start --fixed-ports
curl http://localhost:8001/health  # Still works
```