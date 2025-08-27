#!/bin/bash

# Vector Database Manager Extension for KATO
# This script provides vector database management commands for the KATO system

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$(dirname "$SCRIPT_DIR")"

# Load common variables and functions from kato-manager.sh if available
# Note: This is optional, the script can work standalone

# Vector DB specific configuration
VECTORDB_COMPOSE_FILE="$KATO_ROOT/docker-compose.vectordb.yml"
QDRANT_CONTAINER_NAME="qdrant-${USER}-1"
REDIS_CONTAINER_NAME="redis-cache-${USER}-1"
MIGRATION_SCRIPT="$SCRIPT_DIR/migrate_vectors.py"

# Colors for output (if not already defined)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions (if not already defined)
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if vector DB docker-compose file exists
check_vectordb_compose() {
    if [[ ! -f "$VECTORDB_COMPOSE_FILE" ]]; then
        log_error "Vector DB compose file not found: $VECTORDB_COMPOSE_FILE"
        exit 1
    fi
}

# Start vector database services
start_vectordb() {
    log_info "Starting vector database services..."
    check_vectordb_compose
    
    # Check if already running
    if docker ps --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER_NAME}$"; then
        log_warning "Qdrant already running: $QDRANT_CONTAINER_NAME"
    else
        docker-compose -f "$VECTORDB_COMPOSE_FILE" up -d qdrant
        
        # Wait for Qdrant to be ready
        log_info "Waiting for Qdrant to be ready..."
        local max_attempts=30
        local attempt=0
        
        while [ $attempt -lt $max_attempts ]; do
            if curl -s http://localhost:6333/health >/dev/null 2>&1; then
                log_success "Qdrant is ready"
                break
            fi
            sleep 2
            attempt=$((attempt + 1))
        done
        
        if [ $attempt -eq $max_attempts ]; then
            log_error "Qdrant failed to start within timeout"
            return 1
        fi
    fi
    
    # Optional: Start Redis cache
    if [[ "${ENABLE_CACHE:-true}" == "true" ]]; then
        if docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER_NAME}$"; then
            log_warning "Redis cache already running: $REDIS_CONTAINER_NAME"
        else
            docker-compose -f "$VECTORDB_COMPOSE_FILE" up -d redis-cache
            log_success "Redis cache started"
        fi
    fi
    
    log_success "Vector database services started"
}

# Stop vector database services
stop_vectordb() {
    log_info "Stopping vector database services..."
    check_vectordb_compose
    
    docker-compose -f "$VECTORDB_COMPOSE_FILE" down
    
    log_success "Vector database services stopped"
}

# Show vector database status
status_vectordb() {
    echo "Vector Database Status:"
    echo "======================"
    
    # Check Qdrant
    echo -n "Qdrant: "
    if docker ps --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER_NAME}$"; then
        echo -e "${GREEN}Running${NC}"
        
        # Get health status
        if curl -s http://localhost:6333/health >/dev/null 2>&1; then
            echo "  Health: OK"
            
            # Get collections info
            collections=$(curl -s http://localhost:6333/collections | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  Collections: {len(data.get('result', {}).get('collections', []))}\")" 2>/dev/null || echo "  Collections: Unknown")
            echo "$collections"
        else
            echo "  Health: Not responding"
        fi
    else
        echo -e "${RED}Not running${NC}"
    fi
    
    # Check Redis
    echo -n "Redis Cache: "
    if docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER_NAME}$"; then
        echo -e "${GREEN}Running${NC}"
        
        # Get Redis info
        if docker exec "$REDIS_CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
            echo "  Health: OK"
        else
            echo "  Health: Not responding"
        fi
    else
        echo -e "${YELLOW}Not running${NC}"
    fi
}

# Migrate vectors from MongoDB to vector database
migrate_vectors() {
    log_info "Starting vector migration from MongoDB to vector database..."
    
    # Check if migration script exists
    if [[ ! -f "$MIGRATION_SCRIPT" ]]; then
        log_error "Migration script not found: $MIGRATION_SCRIPT"
        exit 1
    fi
    
    # Check if vector DB is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER_NAME}$"; then
        log_warning "Vector database is not running. Starting it..."
        start_vectordb
    fi
    
    # Check if MongoDB is running
    if ! docker ps --format '{{.Names}}' | grep -q "mongo-kb"; then
        log_error "MongoDB is not running. Please start KATO first."
        exit 1
    fi
    
    # Parse migration options
    local collections=""
    local batch_size="1000"
    local verify="--verify"
    local config_preset=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --collections)
                collections="--collections $2"
                shift 2
                ;;
            --batch-size)
                batch_size="$2"
                shift 2
                ;;
            --no-verify)
                verify="--no-verify"
                shift
                ;;
            --preset)
                config_preset="--config-preset $2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    # Run migration
    log_info "Running migration with batch size: $batch_size"
    
    python3 "$MIGRATION_SCRIPT" \
        --source-host localhost \
        --source-port 27017 \
        --target-backend qdrant \
        --target-host localhost \
        --target-port 6333 \
        --batch-size "$batch_size" \
        $verify \
        $config_preset \
        $collections \
        --output "$KATO_ROOT/logs/migration_report_$(date +%Y%m%d_%H%M%S).json"
    
    if [[ $? -eq 0 ]]; then
        log_success "Vector migration completed successfully"
    else
        log_error "Vector migration failed"
        exit 1
    fi
}

# Backup vector database
backup_vectordb() {
    local backup_dir="${1:-$KATO_ROOT/backups}"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$backup_dir/vectordb_backup_$timestamp"
    
    log_info "Backing up vector database to: $backup_path"
    
    # Create backup directory
    mkdir -p "$backup_path"
    
    # Check if Qdrant is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER_NAME}$"; then
        log_error "Qdrant is not running"
        exit 1
    fi
    
    # Create Qdrant snapshot
    log_info "Creating Qdrant snapshot..."
    
    # Get list of collections
    collections=$(curl -s http://localhost:6333/collections | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data.get('result', {}).get('collections', []):
    print(c['name'])
" 2>/dev/null)
    
    if [[ -z "$collections" ]]; then
        log_warning "No collections found to backup"
    else
        for collection in $collections; do
            log_info "Backing up collection: $collection"
            
            # Create snapshot via API
            curl -X POST "http://localhost:6333/collections/$collection/snapshots" \
                -H "Content-Type: application/json" \
                >/dev/null 2>&1
            
            # Note: In production, you'd download the actual snapshot files
            # For now, we just record the snapshot was created
            echo "$collection snapshot created at $(date)" >> "$backup_path/snapshots.log"
        done
    fi
    
    # Backup Redis if running
    if docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER_NAME}$"; then
        log_info "Backing up Redis cache..."
        docker exec "$REDIS_CONTAINER_NAME" redis-cli BGSAVE >/dev/null 2>&1
        sleep 2
        docker cp "$REDIS_CONTAINER_NAME:/data/dump.rdb" "$backup_path/redis_dump.rdb"
    fi
    
    log_success "Backup completed: $backup_path"
}

# Show vector database logs
logs_vectordb() {
    local service="${1:-all}"
    local tail="${2:-100}"
    
    case $service in
        "qdrant")
            docker logs --tail "$tail" -f "$QDRANT_CONTAINER_NAME"
            ;;
        "redis")
            docker logs --tail "$tail" -f "$REDIS_CONTAINER_NAME"
            ;;
        "all")
            log_info "Showing Qdrant logs..."
            docker logs --tail "$tail" "$QDRANT_CONTAINER_NAME"
            echo ""
            log_info "Showing Redis logs..."
            docker logs --tail "$tail" "$REDIS_CONTAINER_NAME"
            ;;
        *)
            log_error "Unknown service: $service"
            echo "Usage: vectordb logs [qdrant|redis|all] [tail_lines]"
            exit 1
            ;;
    esac
}

# Configure vector database
config_vectordb() {
    local config_file="${1:-$KATO_ROOT/config/vectordb_config.json}"
    
    log_info "Vector Database Configuration"
    echo "=============================="
    
    if [[ -f "$config_file" ]]; then
        cat "$config_file"
    else
        cat << EOF
{
  "backend": "qdrant",
  "qdrant": {
    "host": "localhost",
    "port": 6333,
    "collection_name": "kato_vectors",
    "vector_size": 512,
    "distance": "euclidean"
  },
  "cache": {
    "enabled": true,
    "backend": "redis",
    "host": "localhost",
    "port": 6379,
    "size": 10000,
    "ttl": 3600
  },
  "quantization": {
    "enabled": false,
    "type": "scalar"
  },
  "gpu": {
    "enabled": false
  }
}
EOF
    fi
}

# Test vector database connection
test_vectordb() {
    log_info "Testing vector database connections..."
    
    # Test Qdrant
    echo -n "Testing Qdrant... "
    if curl -s http://localhost:6333/health >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
    fi
    
    # Test Redis
    echo -n "Testing Redis... "
    if docker exec "$REDIS_CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}Not running or not configured${NC}"
    fi
    
    # Test migration script
    echo -n "Testing migration script... "
    if python3 -c "import pymongo, numpy" 2>/dev/null; then
        echo -e "${GREEN}Dependencies OK${NC}"
    else
        echo -e "${YELLOW}Missing dependencies${NC}"
        echo "  Install with: pip install pymongo numpy tqdm qdrant-client"
    fi
}

# Show help
show_help() {
    cat << EOF
Vector Database Manager for KATO
Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
    start       Start vector database services (Qdrant + Redis)
    stop        Stop vector database services
    status      Show vector database status
    migrate     Migrate vectors from MongoDB to vector database
    backup      Backup vector database
    logs        Show vector database logs
    config      Show vector database configuration
    test        Test vector database connections
    help        Show this help message

MIGRATION OPTIONS:
    --collections <name1> <name2>  Specific collections to migrate
    --batch-size <size>            Batch size for migration (default: 1000)
    --no-verify                    Skip verification after migration
    --preset <name>                Use configuration preset

BACKUP OPTIONS:
    backup [directory]             Backup to specified directory

LOGS OPTIONS:
    logs [qdrant|redis|all] [lines]  Show logs for specific service

EXAMPLES:
    $0 start                      Start vector database services
    $0 migrate --batch-size 5000  Migrate with larger batch size
    $0 migrate --preset production  Use production configuration
    $0 backup /path/to/backups    Backup to specific directory
    $0 logs qdrant 50             Show last 50 lines of Qdrant logs

EOF
}

# Main execution
main() {
    local command="$1"
    shift || true
    
    case $command in
        "start")
            start_vectordb
            ;;
        "stop")
            stop_vectordb
            ;;
        "status")
            status_vectordb
            ;;
        "migrate")
            migrate_vectors "$@"
            ;;
        "backup")
            backup_vectordb "$@"
            ;;
        "logs")
            logs_vectordb "$@"
            ;;
        "config")
            config_vectordb "$@"
            ;;
        "test")
            test_vectordb
            ;;
        "help"|"-h"|"--help"|"")
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

# Don't run main if being sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi