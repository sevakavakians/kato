#!/bin/bash

# KATO Manager Script
# Management script for KATO (Knowledge Abstraction for Traceable Outcomes) system
# Author: Generated for KATO project
# Usage: ./kato-manager.sh [command] [options]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$SCRIPT_DIR"
KATO_TESTS_DIR="$KATO_ROOT/tests"
CONFIG_DIR="$KATO_TESTS_DIR/config"
LOGS_DIR="$KATO_ROOT/logs"

# Instance management
KATO_HOME="${HOME}/.kato"
INSTANCES_FILE="${KATO_HOME}/instances.json"
CONFIGS_DIR="${KATO_HOME}/configs"

# Docker configuration
DOCKER_IMAGE_NAME="kato"
DOCKER_TAG="latest"
DOCKER_NETWORK="kato-network"
MONGO_CONTAINER_NAME=""  # Will be set dynamically based on processor ID
QDRANT_CONTAINER_NAME=""  # Will be set dynamically based on processor ID
REDIS_CONTAINER_NAME=""  # Will be set dynamically based on processor ID
KATO_CONTAINER_NAME=""  # Will be set dynamically based on processor ID
MONGO_DB_PORT="27017"
QDRANT_PORT="6333"
REDIS_PORT="6379"
KATO_API_PORT="8000"
KATO_ZMQ_PORT="5555"
CONFIG_FILE="/tmp/kato-config-${USER}.json"

# Default KATO configuration
DEFAULT_API_KEY="ABCD-1234"
DEFAULT_LOG_LEVEL="INFO"

# Default KATO processor parameters
DEFAULT_PROCESSOR_ID="kato-$(date +%s)-$$"  # Include PID for uniqueness
DEFAULT_PROCESSOR_NAME="KatoProcessor"
DEFAULT_INDEXER_TYPE="VI"
DEFAULT_MAX_PATTERN_LENGTH=0
DEFAULT_PERSISTENCE=5
DEFAULT_SMOOTHNESS=3
DEFAULT_AUTO_ACT_METHOD="none"
DEFAULT_AUTO_ACT_THRESHOLD=0.8
DEFAULT_ALWAYS_UPDATE_FREQUENCIES=false
DEFAULT_MAX_PREDICTIONS=100
DEFAULT_RECALL_THRESHOLD=0.1
DEFAULT_QUIESCENCE=3
DEFAULT_SEARCH_DEPTH=10
DEFAULT_SORT=true
DEFAULT_PROCESS_PREDICTIONS=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure required directories exist
mkdir -p "$LOGS_DIR"
mkdir -p "$KATO_HOME"
mkdir -p "$CONFIGS_DIR"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOGS_DIR/kato-manager.log"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOGS_DIR/kato-manager.log"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOGS_DIR/kato-manager.log"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOGS_DIR/kato-manager.log"
}

# Instance Registry Management Functions
init_registry() {
    if [[ ! -f "$INSTANCES_FILE" ]]; then
        echo '{"instances": {}}' > "$INSTANCES_FILE"
        log_info "Initialized instance registry at $INSTANCES_FILE"
    fi
}

# Read instance data from registry
get_instance() {
    local instance_id="$1"
    init_registry
    python3 -c "
import json
with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instance = data.get('instances', {}).get('$instance_id')
    if instance:
        print(json.dumps(instance))
"
}

# Add or update instance in registry
register_instance() {
    local instance_id="$1"
    local name="$2"
    local container="$3"
    local api_port="$4"
    local zmq_port="$5"
    local status="$6"
    
    init_registry
    python3 -c "
import json
from datetime import datetime

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)

if 'instances' not in data:
    data['instances'] = {}

data['instances']['$instance_id'] = {
    'name': '$name',
    'container': '$container',
    'api_port': $api_port,
    'zmq_port': $zmq_port,
    'status': '$status',
    'updated': datetime.now().isoformat()
}

with open('$INSTANCES_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
    log_info "Registered instance: $instance_id ($name) on ports $api_port/$zmq_port"
}

# Remove instance from registry
unregister_instance() {
    local instance_id="$1"
    init_registry
    python3 -c "
import json

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)

if 'instances' in data and '$instance_id' in data['instances']:
    del data['instances']['$instance_id']
    
with open('$INSTANCES_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
    log_info "Unregistered instance: $instance_id"
}

# List all instances
list_instances() {
    init_registry
    echo ""
    echo "KATO Instances:"
    echo "==============="
    python3 -c "
import json
import sys

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instances = data.get('instances', {})
    
if not instances:
    print('No instances registered.')
    sys.exit(0)
    
print(f'{'ID':<20} {'Name':<20} {'Status':<10} {'API Port':<10} {'ZMQ Port':<10} {'Container':<30}')
print('-' * 100)

for instance_id, info in instances.items():
    print(f\"{instance_id:<20} {info['name']:<20} {info['status']:<10} {info['api_port']:<10} {info['zmq_port']:<10} {info['container']:<30}\")
"
    echo ""
}

# List instances with their associated databases
list_instances_with_databases() {
    init_registry
    echo "KATO Instances and Databases:"
    echo "==============================="
    
    if [[ ! -f "$INSTANCES_FILE" ]]; then
        echo "No instances registered."
        return
    fi
    
    python3 -c "
import json
import subprocess

def get_container_status(container_name):
    try:
        result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}:{{.Status}}'], 
                              capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if line.startswith(container_name + ':'):
                return 'running' if 'Up' in line else 'stopped'
        return 'not_found'
    except:
        return 'unknown'

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instances = data.get('instances', {})

if not instances:
    print('No instances registered.')
else:
    for proc_id, info in instances.items():
        # Check container statuses
        kato_status = get_container_status(info['container'])
        mongo_status = get_container_status(f'mongo-{proc_id}')
        qdrant_status = get_container_status(f'qdrant-{proc_id}')
        redis_status = get_container_status(f'redis-{proc_id}')
        
        # Display instance info
        print(f'\nInstance: {proc_id} ({info[\"name\"]})')
        print(f'  KATO:      {info[\"container\"][:40]} ({kato_status})')
        print(f'  MongoDB:   mongo-{proc_id[:35]} ({mongo_status})')
        print(f'  Qdrant:    qdrant-{proc_id[:34]} ({qdrant_status})')
        print(f'  Redis:     redis-{proc_id[:35]} ({redis_status})')
        print(f'  Ports:     API={info[\"api_port\"]}, ZMQ={info[\"zmq_port\"]}')
"
    echo ""
}

# Find next available port
find_available_port() {
    local base_port="$1"
    local port=$base_port
    
    while lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
        port=$((port + 1))
    done
    
    echo $port
}

# Update instance status
update_instance_status() {
    local instance_id="$1"
    local status="$2"
    
    init_registry
    python3 -c "
import json
from datetime import datetime

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)

if 'instances' in data and '$instance_id' in data['instances']:
    data['instances']['$instance_id']['status'] = '$status'
    data['instances']['$instance_id']['updated'] = datetime.now().isoformat()
    
    with open('$INSTANCES_FILE', 'w') as f:
        json.dump(data, f, indent=2)
"
}

# Help function
show_help() {
    cat << EOF
KATO Manager - Management script for KATO AI System

Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
    start       Start a KATO instance with dedicated databases
    stop        Stop and remove KATO instance(s) and their databases
    stop-all    Stop and remove all KATO instances and databases
    restart     Restart KATO instance(s)
    list        List all KATO instances
    status      Show status of KATO instances and their databases
    verify      Verify database connectivity for an instance
    logs        Show logs from KATO containers
    build       Build KATO Docker image
    clean       Clean up Docker containers, images, and volumes
    test        Run KATO test suite
    config      Show current configuration
    shell       Open shell in running KATO container
    diagnose    Run Docker diagnostic to troubleshoot issues
    vectordb    Manage vector database (see: vectordb help)
    
STOP COMMAND OPTIONS:
    stop                     Stop all instances (asks about MongoDB)
    stop <id/name>           Stop specific instance by ID or name
    stop --id <id>           Stop specific instance by ID
    stop --name <name>       Stop specific instance by name
    stop --all               Stop all instances
    stop --all --with-mongo  Stop all instances and MongoDB
    stop --all --no-mongo    Stop all instances, keep MongoDB

BASIC OPTIONS:
    -p, --port PORT         API port (default: $KATO_API_PORT)  
    -t, --tag TAG           Docker image tag (default: $DOCKER_TAG)
    -l, --log-level LEVEL   Log level (DEBUG, INFO, WARNING, ERROR)
    -k, --api-key KEY       API key for authentication
    -h, --help              Show this help message

VECTOR DATABASE OPTIONS:
    --no-vectordb           Disable vector database (use MongoDB only)
    --vectordb-backend TYPE Vector DB backend: qdrant, milvus, weaviate
                           (default: qdrant, starts automatically)

KATO PROCESSOR OPTIONS:
    --id ID                 Processor ID (default: auto-generated)
    --name NAME             Processor name (default: $DEFAULT_PROCESSOR_NAME)
    --indexer-type TYPE     Indexer type: VI (default: $DEFAULT_INDEXER_TYPE)
    --max-seq-length N      Max sequence length (default: $DEFAULT_MAX_PATTERN_LENGTH)
    --persistence N         Persistence value (default: $DEFAULT_PERSISTENCE)
    --smoothness N          Smoothness value (default: $DEFAULT_SMOOTHNESS)
    --auto-act-method M     Auto act method (default: $DEFAULT_AUTO_ACT_METHOD)
    --auto-act-threshold T  Auto act threshold (default: $DEFAULT_AUTO_ACT_THRESHOLD)
    --update-frequencies    Always update frequencies (default: $DEFAULT_ALWAYS_UPDATE_FREQUENCIES)
    --max-predictions N     Max predictions (default: $DEFAULT_MAX_PREDICTIONS)
    --recall-threshold T    Recall threshold (default: $DEFAULT_RECALL_THRESHOLD)
    --quiescence N          Quiescence value (default: $DEFAULT_QUIESCENCE)
    --search-depth N        Search depth (default: $DEFAULT_SEARCH_DEPTH)
    --no-sort              Disable sorting (default: enabled)
    --no-predictions       Disable prediction processing (default: enabled)

EXAMPLES:
    $0 start                                    # Start with defaults and dedicated DBs
    $0 start --no-vectordb                      # Start without vector database
    $0 start --vectordb-backend qdrant          # Explicitly use Qdrant backend
    $0 start --name MyProcessor --port 9000     # Custom name and port
    $0 start --indexer-type VI --max-predictions 50  # Custom indexer
    $0 list                                     # List all instances
    $0 verify mytest                            # Verify databases for instance
    $0 stop P1                                  # Stop instance by name
    $0 stop p5f2b9323c3                        # Stop instance by ID
    $0 stop-all                                 # Stop all instances and databases
    $0 logs kato                                # Show KATO container logs
    $0 test                                     # Run test suite
    $0 clean                                    # Clean everything

EOF
}

# Parse command line arguments
API_PORT="$KATO_API_PORT"
TAG="$DOCKER_TAG"
LOG_LEVEL="$DEFAULT_LOG_LEVEL"
API_KEY="$DEFAULT_API_KEY"

# KATO processor parameters - use environment variables if set, otherwise defaults
PROCESSOR_ID="${PROCESSOR_ID:-$DEFAULT_PROCESSOR_ID}"
PROCESSOR_NAME="${PROCESSOR_NAME:-$DEFAULT_PROCESSOR_NAME}"
INDEXER_TYPE="$DEFAULT_INDEXER_TYPE"
MAX_PATTERN_LENGTH="$DEFAULT_MAX_PATTERN_LENGTH"
PERSISTENCE="$DEFAULT_PERSISTENCE"
SMOOTHNESS="$DEFAULT_SMOOTHNESS"
AUTO_ACT_METHOD="$DEFAULT_AUTO_ACT_METHOD"
AUTO_ACT_THRESHOLD="$DEFAULT_AUTO_ACT_THRESHOLD"
ALWAYS_UPDATE_FREQUENCIES="$DEFAULT_ALWAYS_UPDATE_FREQUENCIES"
MAX_PREDICTIONS="$DEFAULT_MAX_PREDICTIONS"
RECALL_THRESHOLD="$DEFAULT_RECALL_THRESHOLD"
QUIESCENCE="$DEFAULT_QUIESCENCE"
SEARCH_DEPTH="$DEFAULT_SEARCH_DEPTH"
SORT="$DEFAULT_SORT"
PROCESS_PREDICTIONS="$DEFAULT_PROCESS_PREDICTIONS"

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--port)
                API_PORT="$2"
                shift 2
                ;;
            -t|--tag)
                TAG="$2"
                shift 2
                ;;
            -l|--log-level)
                LOG_LEVEL="$2"
                shift 2
                ;;
            -k|--api-key)
                API_KEY="$2"
                shift 2
                ;;
            --id)
                PROCESSOR_ID="$2"
                shift 2
                ;;
            --name)
                PROCESSOR_NAME="$2"
                shift 2
                ;;
            --indexer-type)
                INDEXER_TYPE="$2"
                shift 2
                ;;
            --max-seq-length)
                MAX_PATTERN_LENGTH="$2"
                shift 2
                ;;
            --persistence)
                PERSISTENCE="$2"
                shift 2
                ;;
            --smoothness)
                SMOOTHNESS="$2"
                shift 2
                ;;
            --auto-act-method)
                AUTO_ACT_METHOD="$2"
                shift 2
                ;;
            --auto-act-threshold)
                AUTO_ACT_THRESHOLD="$2"
                shift 2
                ;;
            --update-frequencies)
                ALWAYS_UPDATE_FREQUENCIES="true"
                shift
                ;;
            --max-predictions)
                MAX_PREDICTIONS="$2"
                shift 2
                ;;
            --recall-threshold)
                RECALL_THRESHOLD="$2"
                shift 2
                ;;
            --quiescence)
                QUIESCENCE="$2"
                shift 2
                ;;
            --search-depth)
                SEARCH_DEPTH="$2"
                shift 2
                ;;
            --no-sort)
                SORT="false"
                shift
                ;;
            --no-predictions)
                PROCESS_PREDICTIONS="false"
                shift
                ;;
            --no-vectordb)
                DISABLE_VECTORDB="true"
                shift
                ;;
            --vectordb-backend)
                VECTORDB_BACKEND="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                break
                ;;
        esac
    done
}

# Check dependencies with enhanced Docker detection
check_dependencies() {
    local missing_deps=()
    local docker_found=false
    
    # Method 1: Standard command check
    if command -v docker &> /dev/null; then
        docker_found=true
        log_info "Docker found via command -v: $(command -v docker)"
    else
        # Method 2: Check common installation paths
        local docker_paths=(
            "/usr/bin/docker"
            "/usr/local/bin/docker" 
            "/opt/homebrew/bin/docker"
            "/Applications/Docker.app/Contents/Resources/bin/docker"
        )
        
        for docker_path in "${docker_paths[@]}"; do
            if [[ -x "$docker_path" ]]; then
                docker_found=true
                log_info "Docker found at: $docker_path"
                # Add to PATH for this session
                export PATH="$(dirname "$docker_path"):$PATH"
                break
            fi
        done
    fi
    
    if [[ "$docker_found" == "false" ]]; then
        missing_deps+=("docker")
    else
        # Verify Docker daemon is accessible
        if ! docker version &> /dev/null; then
            log_warning "Docker command found but daemon not accessible"
            log_warning "Make sure Docker Desktop is running or Docker daemon is started"
            # Don't fail here, let user decide
        fi
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_warning "docker-compose not found, using docker commands only"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_error "Please install missing dependencies before running KATO"
        log_error ""
        log_error "Troubleshooting steps:"
        log_error "1. Run './docker-diagnostic.sh' for detailed diagnosis"
        log_error "2. If using Docker Desktop, make sure it's running"
        log_error "3. If using Homebrew: brew install docker"
        log_error "4. Check that Docker is in your PATH"
        exit 1
    fi
}

# Validate parameters
validate_parameters() {
    # Validate indexer type
    if [[ "$INDEXER_TYPE" != "VI" ]]; then
        log_error "Invalid indexer type: $INDEXER_TYPE. Must be VI"
        exit 1
    fi
    
    # Validate numeric parameters
    if ! [[ "$MAX_PATTERN_LENGTH" =~ ^[0-9]+$ ]]; then
        log_error "Invalid max-seq-length: $MAX_PATTERN_LENGTH. Must be a number"
        exit 1
    fi
    
    if ! [[ "$PERSISTENCE" =~ ^[0-9]+$ ]]; then
        log_error "Invalid persistence: $PERSISTENCE. Must be a number"
        exit 1
    fi
    
    if ! [[ "$MAX_PREDICTIONS" =~ ^[0-9]+$ ]]; then
        log_error "Invalid max-predictions: $MAX_PREDICTIONS. Must be a number"
        exit 1
    fi
    
    # Validate threshold values (0.0 to 1.0)
    if ! python3 -c "exit(0 if 0.0 <= float('$RECALL_THRESHOLD') <= 1.0 else 1)" 2>/dev/null; then
        log_error "Invalid recall-threshold: $RECALL_THRESHOLD. Must be between 0.0 and 1.0"
        exit 1
    fi
    
    if ! python3 -c "exit(0 if 0.0 <= float('$AUTO_ACT_THRESHOLD') <= 1.0 else 1)" 2>/dev/null; then
        log_error "Invalid auto-act-threshold: $AUTO_ACT_THRESHOLD. Must be between 0.0 and 1.0"
        exit 1
    fi
    
    log_info "Using processor: $PROCESSOR_NAME (ID: $PROCESSOR_ID)"
    log_info "Max Predictions: $MAX_PREDICTIONS"
}

# Build genome manifest from parameters
build_genome_manifest() {
    cat << EOF
{
  "id": "$PROCESSOR_ID",
  "name": "$PROCESSOR_NAME",
  "indexer_type": "$INDEXER_TYPE",
  "max_pattern_length": $MAX_PATTERN_LENGTH,
  "persistence": $PERSISTENCE,
  "smoothness": $SMOOTHNESS,
  "auto_act_method": "$AUTO_ACT_METHOD",
  "auto_act_threshold": $AUTO_ACT_THRESHOLD,
  "always_update_frequencies": $ALWAYS_UPDATE_FREQUENCIES,
  "max_predictions": $MAX_PREDICTIONS,
  "recall_threshold": $RECALL_THRESHOLD,
  "quiescence": $QUIESCENCE,
  "search_depth": $SEARCH_DEPTH,
  "sort": $SORT,
  "process_predictions": $PROCESS_PREDICTIONS
}
EOF
}

# Docker network management
ensure_network() {
    if ! docker network ls | grep -q "$DOCKER_NETWORK"; then
        log_info "Creating Docker network: $DOCKER_NETWORK"
        docker network create "$DOCKER_NETWORK"
    fi
}

# Container status check
container_status() {
    local container_name="$1"
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container_name"; then
        echo "running"
    elif docker ps -a --format "table {{.Names}}\t{{.Status}}" | grep -q "$container_name"; then
        echo "stopped"
    else
        echo "not_found"
    fi
}

# Start dedicated MongoDB for instance
start_mongodb() {
    local processor_id="$1"
    local container_name="mongo-${processor_id}"
    MONGO_CONTAINER_NAME="$container_name"  # Update global variable
    
    local status=$(container_status "$container_name")
    
    case $status in
        "running")
            log_info "MongoDB already running: $container_name"
            ;;
        "stopped")
            log_info "Starting existing MongoDB container: $container_name"
            docker start "$container_name"
            ;;
        "not_found")
            log_info "Creating MongoDB container for instance: $container_name"
            docker run -d \
                --name "$container_name" \
                --network "$DOCKER_NETWORK" \
                mongo:7.0
            ;;
    esac
    
    # Wait for MongoDB to be ready
    log_info "Waiting for MongoDB to be ready..."
    local retries=30
    while ! docker exec "$container_name" mongosh --eval "db.adminCommand('ping')" &> /dev/null; do
        retries=$((retries - 1))
        if [[ $retries -eq 0 ]]; then
            log_error "MongoDB failed to start"
            return 1
        fi
        sleep 1
    done
    log_success "MongoDB $container_name is ready"
}

# Start dedicated Qdrant for instance
start_qdrant() {
    local processor_id="$1"
    local container_name="qdrant-${processor_id}"
    QDRANT_CONTAINER_NAME="$container_name"  # Update global variable
    
    local status=$(container_status "$container_name")
    
    case $status in
        "running")
            log_info "Qdrant already running: $container_name"
            ;;
        "stopped")
            log_info "Starting existing Qdrant container: $container_name"
            docker start "$container_name"
            ;;
        "not_found")
            log_info "Creating Qdrant container for instance: $container_name"
            docker run -d \
                --name "$container_name" \
                --network "$DOCKER_NETWORK" \
                qdrant/qdrant:latest
            ;;
    esac
    
    # Wait for Qdrant to be ready
    log_info "Waiting for Qdrant to be ready..."
    # Qdrant typically starts very quickly, just give it a few seconds
    sleep 3
    # Check if container is still running
    if [[ $(container_status "$container_name") == "running" ]]; then
        log_success "Qdrant $container_name is ready"
    else
        log_error "Qdrant container failed to start"
        return 1
    fi
}

# Start dedicated Redis for instance
start_redis() {
    local processor_id="$1"
    local container_name="redis-${processor_id}"
    REDIS_CONTAINER_NAME="$container_name"  # Update global variable
    
    local status=$(container_status "$container_name")
    
    case $status in
        "running")
            log_info "Redis already running: $container_name"
            ;;
        "stopped")
            log_info "Starting existing Redis container: $container_name"
            docker start "$container_name"
            ;;
        "not_found")
            log_info "Creating Redis container for instance: $container_name"
            docker run -d \
                --name "$container_name" \
                --network "$DOCKER_NETWORK" \
                redis:7-alpine
            ;;
    esac
    
    # Wait for Redis to be ready
    log_info "Waiting for Redis to be ready..."
    local retries=30
    while ! docker exec "$container_name" redis-cli ping &> /dev/null; do
        retries=$((retries - 1))
        if [[ $retries -eq 0 ]]; then
            log_error "Redis failed to start"
            return 1
        fi
        sleep 1
    done
    log_success "Redis $container_name is ready"
}

# Start KATO with dedicated databases
start_kato() {
    # Set container names based on processor ID
    local clean_id="${PROCESSOR_ID//[^a-zA-Z0-9-]/_}"
    KATO_CONTAINER_NAME="kato-${clean_id}"
    
    # Start dedicated database instances for this KATO instance
    log_info "Starting dedicated database instances for $PROCESSOR_ID..."
    if ! start_mongodb "$clean_id"; then
        log_error "Failed to start MongoDB for instance"
        return 1
    fi
    if ! start_qdrant "$clean_id"; then
        log_error "Failed to start Qdrant for instance"
        # Clean up MongoDB since Qdrant failed
        docker stop "mongo-${clean_id}" 2>/dev/null || true
        docker rm "mongo-${clean_id}" 2>/dev/null || true
        return 1
    fi
    if ! start_redis "$clean_id"; then
        log_error "Failed to start Redis for instance"
        # Clean up MongoDB and Qdrant since Redis failed
        docker stop "mongo-${clean_id}" 2>/dev/null || true
        docker rm "mongo-${clean_id}" 2>/dev/null || true
        docker stop "qdrant-${clean_id}" 2>/dev/null || true
        docker rm "qdrant-${clean_id}" 2>/dev/null || true
        return 1
    fi
    
    # Find available ports if not specified
    if [[ "$API_PORT" == "$KATO_API_PORT" ]]; then
        # Check if default port is in use
        if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            local new_port=$(find_available_port $API_PORT)
            log_warning "Port $API_PORT is in use. Using port $new_port instead."
            API_PORT=$new_port
        fi
    fi
    
    # Find available ZMQ port
    local zmq_port=$KATO_ZMQ_PORT
    if lsof -Pi :$zmq_port -sTCP:LISTEN -t >/dev/null 2>&1; then
        zmq_port=$(find_available_port $KATO_ZMQ_PORT)
    fi
    
    local status=$(container_status "$KATO_CONTAINER_NAME")
    local need_readiness_check=1
    
    case $status in
        "running")
            log_warning "KATO already running: $KATO_CONTAINER_NAME"
            return 0
            ;;
        "stopped")
            log_info "Starting existing KATO container: $KATO_CONTAINER_NAME"
            docker start "$KATO_CONTAINER_NAME"
            ;;
        "not_found")
            # Create new container
            log_info "Creating and starting KATO container: $KATO_CONTAINER_NAME"
            log_info "Using processor: $PROCESSOR_NAME (ID: $PROCESSOR_ID)"
            
            # Build genome manifest from parameters
            local genome_content
            genome_content=$(build_genome_manifest)
            
            # Save configuration to file for status command
            cat > "$CONFIG_FILE" <<EOF
{
    "processor_id": "$PROCESSOR_ID",
    "processor_name": "$PROCESSOR_NAME",
    "indexer_type": "$INDEXER_TYPE",
    "max_predictions": $MAX_PREDICTIONS,
    "recall_threshold": $RECALL_THRESHOLD,
    "persistence": $PERSISTENCE,
    "search_depth": $SEARCH_DEPTH,
    "log_level": "$LOG_LEVEL",
    "tag": "$TAG"
}
EOF
            
            docker run -d \
                --name "$KATO_CONTAINER_NAME" \
                --network "$DOCKER_NETWORK" \
                -p "$API_PORT:8000" \
                -p "$zmq_port:5555" \
                -e "HOSTNAME=$KATO_CONTAINER_NAME" \
                -e "ZMQ_PORT=5555" \
                -e "REST_PORT=8000" \
                -e "LOG_LEVEL=$LOG_LEVEL" \
                -e "MONGO_BASE_URL=mongodb://mongo-${clean_id}:27017" \
                -e "QDRANT_URL=http://qdrant-${clean_id}:6333" \
                -e "REDIS_URL=redis://redis-${clean_id}:6379" \
                -e "MANIFEST=$genome_content" \
                -e "SOURCES=[]" \
                -e "TARGETS=[]" \
                -e "AS_INPUTS=[]" \
                -e "PROCESSOR_ID=$PROCESSOR_ID" \
                -e "PROCESSOR_NAME=$PROCESSOR_NAME" \
                -e "KATO_ZMQ_IMPLEMENTATION=${KATO_ZMQ_IMPLEMENTATION:-improved}" \
                "$DOCKER_IMAGE_NAME:$TAG"
            
            # Register the instance
            register_instance "$PROCESSOR_ID" "$PROCESSOR_NAME" "$KATO_CONTAINER_NAME" "$API_PORT" "$zmq_port" "starting"
            ;;
    esac
        
    # Wait for KATO to be ready
    log_info "Waiting for KATO API to be ready..."
    local retries=30
    local ping_ready=0
    local fully_ready=0
    
    # Phase 1: Wait for ping endpoint to respond
    while [[ $ping_ready -eq 0 ]]; do
        if curl -s "http://localhost:$API_PORT/kato-api/ping" > /dev/null 2>&1; then
            ping_ready=1
            log_info "KATO API is responding to ping"
        else
            retries=$((retries - 1))
            if [[ $retries -eq 0 ]]; then
                log_error "KATO API failed to start (ping timeout)"
                show_logs "kato"
                return 1
            fi
            sleep 2
        fi
    done
    
    # Phase 2: Verify processor is accessible and matches expected ID
    log_info "Verifying processor $PROCESSOR_ID is accessible..."
    retries=20
    while [[ $fully_ready -eq 0 ]]; do
        # Try to ping the specific processor
        local ping_response=$(curl -s "http://localhost:$API_PORT/$PROCESSOR_ID/ping" 2>/dev/null)
        local ping_status=$?
        
        if [[ $ping_status -eq 0 ]] && [[ ! -z "$ping_response" ]]; then
            # Check if the processor ID matches (handle JSON with spaces)
            local returned_id=$(echo "$ping_response" | grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
            if [[ "$returned_id" == "$PROCESSOR_ID" ]]; then
                log_info "Processor ID verified: $PROCESSOR_ID"
                
                # Phase 3: Verify processor can handle operations
                log_info "Testing processor operations..."
                local clear_response=$(curl -s -X POST \
                    -H "X-API-KEY: ABCD-1234" \
                    "http://localhost:$API_PORT/$PROCESSOR_ID/clear-all-memory" 2>/dev/null)
                local clear_status=$?
                
                if [[ $clear_status -eq 0 ]] && [[ "$clear_response" == *"all-cleared"* ]]; then
                    fully_ready=1
                    log_success "KATO processor $PROCESSOR_ID is fully operational on port $API_PORT"
                    # Update instance status to running
                    update_instance_status "$PROCESSOR_ID" "running"
                else
                    log_info "Processor not fully ready yet (clear-memory test failed)"
                fi
            else
                log_info "Processor ID mismatch (expected: $PROCESSOR_ID, got: $returned_id)"
            fi
        else
            log_info "Processor $PROCESSOR_ID not yet accessible"
        fi
        
        if [[ $fully_ready -eq 0 ]]; then
            retries=$((retries - 1))
            if [[ $retries -eq 0 ]]; then
                log_error "KATO processor failed to become fully operational"
                show_logs "kato"
                return 1
            fi
            sleep 3
        fi
    done
    
    # Give it one more second for any final initialization
    sleep 1
}

# Find instance by ID or name
find_instance() {
    local search_term="$1"
    init_registry
    
    # First try to find by ID, then by name
    python3 -c "
import json
import sys

search_term = '$search_term'

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instances = data.get('instances', {})
    
# First check if it's an exact ID match
if search_term in instances:
    print(search_term)
    sys.exit(0)

# Then check by name
for instance_id, info in instances.items():
    if info.get('name', '') == search_term:
        print(instance_id)
        sys.exit(0)

# No match found
sys.exit(1)
"
}

# Stop specific instance and all associated databases
stop_instance() {
    local search_term="$1"
    local remove_container="${2:-true}"  # Default to removing container
    
    if [[ -z "$search_term" ]]; then
        log_error "Instance ID or name required. Use 'list' command to see available instances."
        return 1
    fi
    
    # Find instance by ID or name
    local instance_id=$(find_instance "$search_term")
    
    if [[ -z "$instance_id" ]]; then
        log_error "Instance not found: $search_term"
        return 1
    fi
    
    # Get instance info from registry
    local instance_info=$(get_instance "$instance_id")
    
    if [[ -z "$instance_info" ]]; then
        log_error "Instance not found in registry: $instance_id"
        return 1
    fi
    
    local container=$(echo "$instance_info" | python3 -c "import sys, json; print(json.load(sys.stdin)['container'])")
    local name=$(echo "$instance_info" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', 'Unknown'))")
    
    log_info "Stopping instance and all associated databases: $instance_id ($name)"
    
    # Extract clean ID from container name
    local clean_id="${container#kato-}"
    
    # Stop and remove KATO container
    if [[ $(container_status "$container") != "not_found" ]]; then
        docker stop "$container" >/dev/null 2>&1
        docker rm "$container" >/dev/null 2>&1
        log_success "KATO container removed: $container"
    fi
    
    # Stop and remove associated MongoDB
    local mongo_container="mongo-${clean_id}"
    if [[ $(container_status "$mongo_container") != "not_found" ]]; then
        docker stop "$mongo_container" >/dev/null 2>&1
        docker rm "$mongo_container" >/dev/null 2>&1
        log_success "MongoDB removed: $mongo_container"
    fi
    
    # Stop and remove associated Qdrant
    local qdrant_container="qdrant-${clean_id}"
    if [[ $(container_status "$qdrant_container") != "not_found" ]]; then
        docker stop "$qdrant_container" >/dev/null 2>&1
        docker rm "$qdrant_container" >/dev/null 2>&1
        log_success "Qdrant removed: $qdrant_container"
    fi
    
    # Stop and remove associated Redis
    local redis_container="redis-${clean_id}"
    if [[ $(container_status "$redis_container") != "not_found" ]]; then
        docker stop "$redis_container" >/dev/null 2>&1
        docker rm "$redis_container" >/dev/null 2>&1
        log_success "Redis removed: $redis_container"
    fi
    
    # Remove from registry
    unregister_instance "$instance_id"
    
    log_success "Instance and all databases cleaned up: $instance_id ($name)"
}

# Stop all instances
stop_all_instances() {
    init_registry
    
    local stop_mongo="${1:-ask}"  # Default to asking about MongoDB
    
    log_info "Stopping and removing all KATO instances..."
    
    # Get list of instance IDs
    local instance_ids=$(python3 -c "
import json

with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instances = data.get('instances', {})
    
for instance_id in instances:
    print(instance_id)
")
    
    if [[ -z "$instance_ids" ]]; then
        log_info "No instances to stop"
    else
        # Stop each instance
        echo "$instance_ids" | while read instance_id; do
            if [[ ! -z "$instance_id" ]]; then
                stop_instance "$instance_id" "true"  # Force remove containers
            fi
        done
        log_success "All instances stopped and removed"
    fi
    
    # Handle shared databases (legacy cleanup)
    if [[ "$stop_mongo" == "yes" ]]; then
        stop_shared_databases
    elif [[ "$stop_mongo" == "ask" ]]; then
        read -p "Stop and remove any shared database containers? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            stop_shared_databases
        fi
    fi
}

# Stop all shared database instances (legacy cleanup)
stop_shared_databases() {
    log_info "Stopping any shared database containers..."
    
    # Stop shared MongoDB instances
    docker ps --format "{{.Names}}" | grep -E "^mongo-kb-" | while read container; do
        docker stop "$container" >/dev/null 2>&1
        docker rm "$container" >/dev/null 2>&1
        log_success "Removed shared MongoDB: $container"
    done
    
    # Stop shared Qdrant instances
    docker ps --format "{{.Names}}" | grep -E "^qdrant-.*-1$" | while read container; do
        docker stop "$container" >/dev/null 2>&1
        docker rm "$container" >/dev/null 2>&1
        log_success "Removed shared Qdrant: $container"
    done
    
    # Stop shared Redis instances
    docker ps --format "{{.Names}}" | grep -E "^redis-cache-" | while read container; do
        docker stop "$container" >/dev/null 2>&1
        docker rm "$container" >/dev/null 2>&1
        log_success "Removed shared Redis: $container"
    done
}

# Stop services - enhanced with better parameter handling
stop_services() {
    local target=""
    local stop_mongo="ask"
    
    # Parse stop command parameters
    while [[ $# -gt 0 ]]; do
        case $1 in
            --id|--name)
                target="$2"
                shift 2
                ;;
            --all)
                target="all"
                shift
                ;;
            --with-mongo)
                stop_mongo="yes"
                shift
                ;;
            --no-mongo)
                stop_mongo="no"
                shift
                ;;
            *)
                # If no flag, assume it's an ID or name
                if [[ -z "$target" ]]; then
                    target="$1"
                fi
                shift
                ;;
        esac
    done
    
    # Determine what to stop
    if [[ "$target" == "all" ]] || [[ -z "$target" ]]; then
        # Stop all instances
        stop_all_instances "$stop_mongo"
    else
        # Stop specific instance by ID or name
        stop_instance "$target" "true"
    fi
}

# Show status
show_status() {
    echo
    log_info "KATO System Status"
    echo "===================="
    
    # Show instances with their dedicated databases
    echo
    list_instances_with_databases
    
    echo
    echo "Network:"
    echo "-------"
    if docker network ls | grep -q "$DOCKER_NETWORK"; then
        echo "Docker network: $DOCKER_NETWORK (exists)"
    else
        echo "Docker network: $DOCKER_NETWORK (not found)"
    fi
    
    echo
    echo "Ports:"
    echo "-----"
    printf "%-20s %s\n" "KATO API:" "$API_PORT"
    printf "%-20s %s\n" "MongoDB:" "$MONGO_DB_PORT"
    
    echo
    echo "Configuration:"
    echo "-------------"
    
    # Try to get configuration from multiple sources
    local show_processor_id=""
    local show_processor_name=""
    local show_indexer_type=""
    local show_max_predictions=""
    local show_recall_threshold=""
    
    # First, try to load from saved config file
    if [[ -f "$CONFIG_FILE" ]]; then
        show_processor_id=$(grep '"processor_id"' "$CONFIG_FILE" 2>/dev/null | sed 's/.*"processor_id": *"\([^"]*\)".*/\1/')
        show_processor_name=$(grep '"processor_name"' "$CONFIG_FILE" 2>/dev/null | sed 's/.*"processor_name": *"\([^"]*\)".*/\1/')
        show_indexer_type=$(grep '"indexer_type"' "$CONFIG_FILE" 2>/dev/null | sed 's/.*"indexer_type": *"\([^"]*\)".*/\1/')
        show_max_predictions=$(grep '"max_predictions"' "$CONFIG_FILE" 2>/dev/null | sed 's/.*"max_predictions": *\([0-9]*\).*/\1/')
        show_recall_threshold=$(grep '"recall_threshold"' "$CONFIG_FILE" 2>/dev/null | sed 's/.*"recall_threshold": *\([0-9.]*\).*/\1/')
    fi
    
    # If container is running, verify/override with actual container configuration
    if [[ "$kato_status" == "running" ]]; then
        # Extract configuration from running container's environment variables
        local actual_processor_id=$(docker inspect "$KATO_CONTAINER_NAME" 2>/dev/null | grep '"PROCESSOR_ID=' | sed 's/.*"PROCESSOR_ID=\([^"]*\)".*/\1/')
        local actual_processor_name=$(docker inspect "$KATO_CONTAINER_NAME" 2>/dev/null | grep '"PROCESSOR_NAME=' | sed 's/.*"PROCESSOR_NAME=\([^"]*\)".*/\1/')
        
        # Extract from MANIFEST JSON if individual vars are not found
        if [[ -z "$actual_processor_id" ]] || [[ -z "$actual_processor_name" ]]; then
            local manifest=$(docker inspect "$KATO_CONTAINER_NAME" 2>/dev/null | grep '"MANIFEST=' | sed 's/.*"MANIFEST=\(.*\)",$/\1/' | sed 's/\\n//g' | sed 's/\\"/"/g')
            if [[ -n "$manifest" ]]; then
                actual_processor_id=$(echo "$manifest" | sed -n 's/.*"id": *"\([^"]*\)".*/\1/p')
                actual_processor_name=$(echo "$manifest" | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p')
                local actual_indexer_type=$(echo "$manifest" | sed -n 's/.*"indexer_type": *"\([^"]*\)".*/\1/p')
                local actual_max_predictions=$(echo "$manifest" | sed -n 's/.*"max_predictions": *\([0-9]*\).*/\1/p')
                local actual_recall_threshold=$(echo "$manifest" | sed -n 's/.*"recall_threshold": *\([0-9.]*\).*/\1/p')
            fi
        fi
        
        # Use actual values from container if found
        [[ -n "$actual_processor_id" ]] && show_processor_id="$actual_processor_id"
        [[ -n "$actual_processor_name" ]] && show_processor_name="$actual_processor_name"
        [[ -n "$actual_indexer_type" ]] && show_indexer_type="$actual_indexer_type"
        [[ -n "$actual_max_predictions" ]] && show_max_predictions="$actual_max_predictions"
        [[ -n "$actual_recall_threshold" ]] && show_recall_threshold="$actual_recall_threshold"
    fi
    
    # Display configuration with fallback to defaults
    printf "%-20s %s\n" "Processor Name:" "${show_processor_name:-$PROCESSOR_NAME}"
    printf "%-20s %s\n" "Processor ID:" "${show_processor_id:-$PROCESSOR_ID}"
    printf "%-20s %s\n" "Indexer Type:" "${show_indexer_type:-$INDEXER_TYPE}"
    printf "%-20s %s\n" "Max Predictions:" "${show_max_predictions:-$MAX_PREDICTIONS}"
    printf "%-20s %s\n" "Recall Threshold:" "${show_recall_threshold:-$RECALL_THRESHOLD}"
    
    printf "%-20s %s\n" "Log Level:" "$LOG_LEVEL"
    printf "%-20s %s\n" "Docker Tag:" "$TAG"
    
    if [[ "$kato_status" == "running" ]]; then
        echo
        echo "API Endpoints:"
        echo "-------------"
        echo "Health Check: http://localhost:$API_PORT/kato-api/ping"
        echo "API Base URL: http://localhost:$API_PORT"
    fi
}

# Show logs
show_logs() {
    local service="$1"
    local lines="${2:-50}"
    
    case $service in
        "kato"|"api")
            if [[ $(container_status "$KATO_CONTAINER_NAME") != "not_found" ]]; then
                log_info "Showing last $lines lines of KATO logs:"
                docker logs --tail "$lines" -f "$KATO_CONTAINER_NAME"
            else
                log_error "KATO container not found: $KATO_CONTAINER_NAME"
            fi
            ;;
        "mongo"|"mongodb")
            if [[ $(container_status "$MONGO_CONTAINER_NAME") != "not_found" ]]; then
                log_info "Showing last $lines lines of MongoDB logs:"
                docker logs --tail "$lines" -f "$MONGO_CONTAINER_NAME"
            else
                log_error "MongoDB container not found: $MONGO_CONTAINER_NAME"
            fi
            ;;
        "all"|"")
            echo "=== KATO Logs ==="
            show_logs "kato" "$lines"
            echo
            echo "=== MongoDB Logs ==="
            show_logs "mongo" "$lines"
            ;;
        *)
            log_error "Unknown service: $service"
            log_info "Available services: kato, mongo, all"
            ;;
    esac
}

# Verify instance connectivity
verify_instance() {
    local instance_id="${1:-$PROCESSOR_ID}"
    
    if [[ -z "$instance_id" ]]; then
        log_error "Instance ID required for verification"
        echo "Usage: $0 verify <instance_id>"
        return 1
    fi
    
    log_info "Verifying instance: $instance_id"
    
    # Check if instance is registered
    if [[ ! -f "$INSTANCES_FILE" ]]; then
        log_error "No instances registered"
        return 1
    fi
    
    # Get instance info
    local instance_info=$(python3 -c "
import json
with open('$INSTANCES_FILE', 'r') as f:
    data = json.load(f)
    instances = data.get('instances', {})
    if '$instance_id' in instances:
        info = instances['$instance_id']
        print(f\"{info['api_port']}|{info['container']}|{info['name']}\")
" 2>/dev/null)
    
    if [[ -z "$instance_info" ]]; then
        log_error "Instance not found: $instance_id"
        return 1
    fi
    
    local api_port=$(echo "$instance_info" | cut -d'|' -f1)
    local container=$(echo "$instance_info" | cut -d'|' -f2)
    local name=$(echo "$instance_info" | cut -d'|' -f3)
    
    echo ""
    echo "Testing Instance: $instance_id ($name)"
    echo "========================================"
    
    # Test KATO container
    echo -n "  KATO Container (${container}): "
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        echo "✓ running"
    else
        echo "✗ not running"
        return 1
    fi
    
    # Test MongoDB
    echo -n "  MongoDB (mongo-${instance_id}): "
    if docker ps --format "{{.Names}}" | grep -q "^mongo-${instance_id}$"; then
        # Test actual connectivity
        if docker exec "mongo-${instance_id}" mongo --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
            echo "✓ running and responsive"
        else
            echo "⚠ running but not responsive"
        fi
    else
        echo "✗ not running"
    fi
    
    # Test Qdrant
    echo -n "  Qdrant (qdrant-${instance_id}): "
    if docker ps --format "{{.Names}}" | grep -q "^qdrant-${instance_id}$"; then
        # Test actual connectivity from KATO container
        if docker exec "$container" curl -s "http://qdrant-${instance_id}:6333/health" >/dev/null 2>&1; then
            echo "✓ running and responsive"
        else
            echo "⚠ running but not responsive"
        fi
    else
        echo "✗ not running"
    fi
    
    # Test Redis
    echo -n "  Redis (redis-${instance_id}): "
    if docker ps --format "{{.Names}}" | grep -q "^redis-${instance_id}$"; then
        # Test actual connectivity
        if docker exec "redis-${instance_id}" redis-cli ping >/dev/null 2>&1; then
            echo "✓ running and responsive"
        else
            echo "⚠ running but not responsive"
        fi
    else
        echo "✗ not running"
    fi
    
    # Test KATO API
    echo -n "  KATO API (port ${api_port}): "
    if curl -s "http://localhost:${api_port}/kato-api/ping" >/dev/null 2>&1; then
        echo "✓ responsive"
        
        # Test observe endpoint
        echo -n "  Observe endpoint: "
        local observe_response=$(curl -s -X POST "http://localhost:${api_port}/${instance_id}/observe" \
            -H "Content-Type: application/json" \
            -d '{"observations": [["test_verify"]]}' 2>/dev/null)
        if [[ -n "$observe_response" ]] && [[ "$observe_response" != *"error"* ]]; then
            echo "✓ working"
        else
            echo "✗ failed"
        fi
        
        # Test predict endpoint
        echo -n "  Predict endpoint: "
        local predict_response=$(curl -s -X POST "http://localhost:${api_port}/${instance_id}/predict" \
            -H "Content-Type: application/json" \
            -d '{"observations": [["test_verify"]]}' 2>/dev/null)
        if [[ -n "$predict_response" ]] && [[ "$predict_response" != *"error"* ]]; then
            echo "✓ working"
        else
            echo "✗ failed"
        fi
    else
        echo "✗ not responsive"
    fi
    
    echo ""
    log_success "Verification complete for instance: $instance_id"
}

# Build Docker image
build_image() {
    log_info "Building KATO Docker image: $DOCKER_IMAGE_NAME:$TAG"
    
    if [[ ! -f "$KATO_ROOT/Dockerfile" ]]; then
        log_error "Dockerfile not found in: $KATO_ROOT"
        exit 1
    fi
    
    cd "$KATO_ROOT"
    docker build -t "$DOCKER_IMAGE_NAME:$TAG" .
    log_success "KATO Docker image built successfully"
}

# Clean up
cleanup() {
    log_info "Cleaning up KATO system..."
    
    # Stop and remove containers
    for container in "$KATO_CONTAINER_NAME" "$MONGO_CONTAINER_NAME"; do
        if [[ $(container_status "$container") != "not_found" ]]; then
            log_info "Removing container: $container"
            docker rm -f "$container" 2>/dev/null || true
        fi
    done
    
    # Remove network
    if docker network ls | grep -q "$DOCKER_NETWORK"; then
        log_info "Removing network: $DOCKER_NETWORK"
        docker network rm "$DOCKER_NETWORK" 2>/dev/null || true
    fi
    
    # Optionally remove images
    read -p "Remove KATO Docker images? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker rmi "$DOCKER_IMAGE_NAME:$TAG" 2>/dev/null || true
        docker rmi mongo:4.4 2>/dev/null || true
    fi
    
    # Optionally remove volumes
    read -p "Remove MongoDB data volume? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker volume rm kato-mongo-data 2>/dev/null || true
    fi
    
    log_success "Cleanup completed"
}

# Run tests
run_tests() {
    log_info "Running KATO test suite in container..."
    
    # Check if test-harness.sh exists
    if [[ ! -f "$KATO_ROOT/test-harness.sh" ]]; then
        log_error "test-harness.sh not found in project root"
        exit 1
    fi
    
    # Ensure KATO is running for integration/API tests
    if [[ $(container_status "$KATO_CONTAINER_NAME") != "running" ]]; then
        log_warning "KATO is not running. Starting it for integration tests..."
        ensure_network
        start_mongodb
        start_kato
    else
        log_info "KATO is already running"
    fi
    
    # Build test harness if needed
    if ! docker images | grep -q "kato-test-harness"; then
        log_info "Test harness container not found. Building..."
        "$KATO_ROOT/test-harness.sh" build
    fi
    
    # Run tests using test-harness.sh
    log_info "Running tests in containerized environment..."
    "$KATO_ROOT/test-harness.sh" test "$@" | tee "$LOGS_DIR/test-results.log"
    
    local test_result=${PIPESTATUS[0]}
    if [[ $test_result -eq 0 ]]; then
        log_success "All tests passed"
    else
        log_error "Some tests failed. Check $LOGS_DIR/test-results.log for details"
        exit $test_result
    fi
}

# Open shell in container
open_shell() {
    if [[ $(container_status "$KATO_CONTAINER_NAME") == "running" ]]; then
        log_info "Opening shell in KATO container..."
        docker exec -it "$KATO_CONTAINER_NAME" /bin/bash
    else
        log_error "KATO container is not running"
        log_info "Start KATO first: $0 start"
        exit 1
    fi
}

# Main execution
main() {
    local command="$1"
    shift || true
    
    parse_args "$@"
    check_dependencies
    
    case $command in
        "start")
            validate_parameters
            ensure_network
            # Databases are now started automatically by start_kato
            start_kato
            log_success "KATO system started successfully"
            show_status
            ;;
        "stop")
            stop_services "$@"
            ;;
        "stop-all")
            stop_all_instances "ask"
            ;;
        "restart")
            stop_services "$@"
            sleep 2
            validate_parameters
            ensure_network
            # Databases are now started automatically by start_kato
            start_kato
            log_success "KATO system restarted successfully"
            ;;
        "list")
            list_instances
            ;;
        "status")
            show_status
            ;;
        "verify")
            verify_instance "$1"
            ;;
        "logs")
            show_logs "$1" "$2"
            ;;
        "build")
            # Force rebuild when explicitly requested
            build_image "true"
            ;;
        "clean")
            cleanup
            ;;
        "test")
            run_tests
            ;;
        "config")
            show_status
            echo ""
            echo "Current Parameters:"
            echo "=================="
            echo "Processor ID: $PROCESSOR_ID"
            echo "Processor Name: $PROCESSOR_NAME"
            echo "Max Pattern Length: $MAX_PATTERN_LENGTH"
            echo "Persistence: $PERSISTENCE"
            echo "Smoothness: $SMOOTHNESS"
            echo "Auto Act Method: $AUTO_ACT_METHOD"
            echo "Auto Act Threshold: $AUTO_ACT_THRESHOLD"
            echo "Always Update Frequencies: $ALWAYS_UPDATE_FREQUENCIES"
            echo "Max Predictions: $MAX_PREDICTIONS"
            echo "Recall Threshold: $RECALL_THRESHOLD"
            echo "Quiescence: $QUIESCENCE"
            echo "Search Depth: $SEARCH_DEPTH"
            echo "Sort: $SORT"
            echo "Process Predictions: $PROCESS_PREDICTIONS"
            ;;
        "shell")
            open_shell
            ;;
        "diagnose")
            if [[ -x "./docker-diagnostic.sh" ]]; then
                ./docker-diagnostic.sh
            else
                log_error "docker-diagnostic.sh not found or not executable"
                log_info "Please ensure docker-diagnostic.sh is in the current directory"
            fi
            ;;
        "vectordb")
            # Call vector database manager script
            if [[ -x "$SCRIPT_DIR/scripts/vectordb_manager.sh" ]]; then
                "$SCRIPT_DIR/scripts/vectordb_manager.sh" "$@"
            else
                log_error "Vector database manager not found or not executable"
                log_info "Please ensure scripts/vectordb_manager.sh exists"
                exit 1
            fi
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

# Execute main function
main "$@"
