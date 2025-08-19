# KATO Manager Documentation

The KATO Manager (`kato-manager.sh`) is a comprehensive management script for the KATO AI system. It provides easy-to-use commands for starting, stopping, monitoring, and managing KATO deployments.

## Quick Start

```bash
# Make the script executable
chmod +x kato-manager.sh

# Start KATO system with default settings
./kato-manager.sh start

# Check system status
./kato-manager.sh status

# View logs
./kato-manager.sh logs

# Stop the system
./kato-manager.sh stop
```

## Prerequisites

- Docker (required)
- Docker Compose (optional, for docker-compose.yml support)
- curl (for health checks)

## Commands

### System Management

- **`start`** - Start KATO system with MongoDB backend
- **`stop`** - Stop KATO system and cleanup containers  
- **`restart`** - Restart KATO system
- **`status`** - Show status of containers and services
- **`build`** - Build KATO Docker image
- **`clean`** - Clean up containers, images, and volumes

### Monitoring & Debugging

- **`logs [service]`** - Show logs (services: kato, mongo, all)
- **`shell`** - Open bash shell in running KATO container
- **`test`** - Run KATO test suite

### Configuration

- **`config`** - Show current configuration
- **`genomes`** - List available genome configurations

## Options

- `-g, --genome GENOME` - Specify genome file (default: simple.genome)
- `-p, --port PORT` - API port (default: 8000)
- `-t, --tag TAG` - Docker image tag (default: latest)
- `-l, --log-level LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)
- `-k, --api-key KEY` - API key for authentication
- `-h, --help` - Show help message

## Examples

### Basic Usage
```bash
# Start with default genome
./kato-manager.sh start

# Start with specific genome
./kato-manager.sh start -g decision1.genome

# Start on custom port with debug logging
./kato-manager.sh start -g simple.genome -p 9000 -l DEBUG
```

### Monitoring
```bash
# Show system status
./kato-manager.sh status

# Follow KATO logs
./kato-manager.sh logs kato

# Follow MongoDB logs
./kato-manager.sh logs mongo

# Open shell in container
./kato-manager.sh shell
```

### Development
```bash
# Build new Docker image
./kato-manager.sh build

# Run tests
./kato-manager.sh test

# Clean up everything
./kato-manager.sh clean
```

## Configuration Files

### Genomes
Genome files define the KATO system configuration and are stored in `kato-tests/test-genomes/`. Available formats:
- `.genome` files (JSON format)
- `.json` files

List available genomes:
```bash
./kato-manager.sh genomes
```

### Environment Variables
The script supports these environment variables:
- `KATO_API_PORT` - API port (default: 8000)
- `KATO_LOG_LEVEL` - Log level (default: INFO)
- `DOCKER_TAG` - Docker image tag (default: latest)

### Docker Compose
A `docker-compose.yml` file is provided for easier deployment:
```bash
# Using docker-compose
docker-compose up -d

# Using environment file
cp .env.example .env
# Edit .env as needed
docker-compose up -d
```

## Logs

Logs are stored in the `logs/` directory:
- `kato-manager.log` - Manager script logs
- `test-results.log` - Test execution logs

Container logs can be viewed with:
```bash
./kato-manager.sh logs [service]
```

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   ./kato-manager.sh start -p 9000
   ```

2. **Container won't start**
   ```bash
   ./kato-manager.sh logs kato
   ./kato-manager.sh build
   ./kato-manager.sh restart
   ```

3. **MongoDB connection issues**
   ```bash
   ./kato-manager.sh logs mongo
   ./kato-manager.sh clean
   ./kato-manager.sh start
   ```

4. **Clean slate restart**
   ```bash
   ./kato-manager.sh clean
   ./kato-manager.sh build
   ./kato-manager.sh start
   ```

### Health Checks

The system provides health check endpoints:
- `http://localhost:8000/kato-api/ping` - KATO API health
- MongoDB health is checked internally

### Container Management

Containers are named with user prefix:
- KATO API: `kato-api-${USER}-1`
- MongoDB: `mongo-kb-${USER}-1`

This allows multiple users to run KATO on the same system without conflicts.

## Architecture

The manager script creates:
1. **Docker Network**: `kato-network`
2. **MongoDB Container**: Persistent data storage
3. **KATO API Container**: Main KATO processor
4. **Volume**: `kato-mongo-data` for MongoDB persistence

## Integration

The script can be integrated into CI/CD pipelines:
```bash
# Build and test
./kato-manager.sh build
./kato-manager.sh start -g test.genome
./kato-manager.sh test
./kato-manager.sh stop
```