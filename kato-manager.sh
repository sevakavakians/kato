#!/bin/bash

# KATO Manager Script
# Management script for KATO FastAPI architecture
# Usage: ./kato-manager.sh [command] [options]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$SCRIPT_DIR"
LOGS_DIR="$KATO_ROOT/logs"
COMPOSE_FILE="docker-compose.yml"
DOCKER_IMAGE="kato:latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure required directories exist
mkdir -p "$LOGS_DIR"

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

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
}

# Check if docker-compose is available
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        # Try docker compose (newer integrated version)
        if ! docker compose version &> /dev/null; then
            log_error "docker-compose is not installed"
            exit 1
        fi
        # Use docker compose instead of docker-compose
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
}

# Build Docker image
build_image() {
    log_info "Building KATO Docker image..."
    
    cd "$KATO_ROOT"
    docker build -f Dockerfile -t "$DOCKER_IMAGE" .
    
    if [ $? -eq 0 ]; then
        log_success "Docker image built successfully"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
}

# Start KATO services
start_services() {
    local service_name="${1:-}"
    
    check_docker
    check_docker_compose
    
    # Build image if it doesn't exist
    if ! docker images | grep -q "kato.*latest"; then
        log_warning "Image not found, building..."
        build_image
    fi
    
    log_info "Starting KATO services..."
    
    cd "$KATO_ROOT"
    
    if [ -n "$service_name" ]; then
        # Start specific service
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d "$service_name"
    else
        # Start all services
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d mongodb qdrant
        sleep 5  # Wait for databases
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d kato-primary kato-testing
    fi
    
    if [ $? -eq 0 ]; then
        log_success "KATO services started"
        
        # Wait for services to be ready
        log_info "Waiting for services to be ready..."
        sleep 5
        
        # Show status
        show_status
    else
        log_error "Failed to start services"
        exit 1
    fi
}

# Stop KATO services
stop_services() {
    local service_name="${1:-}"
    
    check_docker
    check_docker_compose
    
    log_info "Stopping KATO services..."
    
    cd "$KATO_ROOT"
    
    if [ -n "$service_name" ]; then
        # Stop specific service
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" stop "$service_name"
    else
        # Stop all services
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" stop
    fi
    
    if [ $? -eq 0 ]; then
        log_success "KATO services stopped"
    else
        log_error "Failed to stop services"
        exit 1
    fi
}

# Restart services
restart_services() {
    local service_name="${1:-}"
    
    stop_services "$service_name"
    sleep 2
    start_services "$service_name"
}

# Show status of services
show_status() {
    check_docker
    check_docker_compose
    
    log_info "KATO FastAPI Services Status:"
    echo ""
    
    cd "$KATO_ROOT"
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps
    
    echo ""
    log_info "Service URLs:"
    echo "  Primary KATO:  http://localhost:8001"
    echo "  Testing KATO:  http://localhost:8002"
    echo "  Analytics KATO: http://localhost:8003"
    echo "  MongoDB:       mongodb://localhost:27017"
    echo "  Qdrant:        http://localhost:6333"
    
    echo ""
    log_info "Health Check:"
    
    # Check each service
    for port in 8001 8002 8003; do
        if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "  Port ${port}: ${GREEN}✓ Healthy${NC}"
        else
            echo -e "  Port ${port}: ${RED}✗ Not responding${NC}"
        fi
    done
}

# View logs
view_logs() {
    local service_name="${1:-}"
    
    check_docker
    check_docker_compose
    
    cd "$KATO_ROOT"
    
    if [ -n "$service_name" ]; then
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" logs -f "$service_name"
    else
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" logs -f
    fi
}

# Clean up containers and volumes
cleanup() {
    check_docker
    check_docker_compose
    
    log_warning "This will remove all KATO containers and volumes!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$KATO_ROOT"
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" down -v
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

# Test the FastAPI implementation
test_fastapi() {
    log_info "Testing KATO FastAPI implementation..."
    
    # Check if services are running
    if ! curl -s "http://localhost:8001/health" > /dev/null 2>&1; then
        log_warning "Services not running, starting them..."
        start_services
    fi
    
    # Run test script
    python3 "$KATO_ROOT/test_fastapi.py"
}

# Run full test suite
run_tests() {
    log_info "Running KATO test suite with FastAPI..."
    
    # Ensure services are running
    if ! curl -s "http://localhost:8002/health" > /dev/null 2>&1; then
        start_services kato-testing
    fi
    
    # Set environment to use FastAPI
    export USE_FASTAPI=true
    export KATO_API_URL="http://localhost:8002"
    
    # Run tests
    cd "$KATO_ROOT"
    ./run_tests.sh
}

# Create a new KATO instance dynamically
create_instance() {
    local instance_name="${1:-}"
    local port="${2:-}"
    
    if [ -z "$instance_name" ]; then
        log_error "Instance name required"
        echo "Usage: $0 create <name> [port]"
        exit 1
    fi
    
    # Find available port if not specified
    if [ -z "$port" ]; then
        port=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")
    fi
    
    check_docker
    
    log_info "Creating new KATO instance: $instance_name on port $port"
    
    # Run new container
    docker run -d \
        --name "kato-${instance_name}" \
        --network kato-network \
        -p "${port}:8000" \
        -e "PROCESSOR_ID=${instance_name}" \
        -e "PROCESSOR_NAME=${instance_name}" \
        -e "MONGO_BASE_URL=mongodb://mongodb:27017" \
        -e "LOG_LEVEL=INFO" \
        "$DOCKER_IMAGE"
    
    if [ $? -eq 0 ]; then
        log_success "Instance created: http://localhost:${port}"
    else
        log_error "Failed to create instance"
        exit 1
    fi
}

# Remove a KATO instance
remove_instance() {
    local instance_name="${1:-}"
    
    if [ -z "$instance_name" ]; then
        log_error "Instance name required"
        echo "Usage: $0 remove <name>"
        exit 1
    fi
    
    check_docker
    
    log_info "Removing KATO instance: $instance_name"
    
    docker stop "kato-${instance_name}" 2>/dev/null || true
    docker rm "kato-${instance_name}" 2>/dev/null || true
    
    log_success "Instance removed"
}

# Show usage information
show_usage() {
    echo "KATO FastAPI Manager"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  build              Build Docker image"
    echo "  start [service]    Start KATO services (or specific service)"
    echo "  stop [service]     Stop KATO services (or specific service)"
    echo "  restart [service]  Restart KATO services"
    echo "  status             Show status of services"
    echo "  logs [service]     View service logs"
    echo "  test               Run FastAPI tests"
    echo "  test-all           Run full test suite"
    echo "  create <name>      Create new KATO instance"
    echo "  remove <name>      Remove KATO instance"
    echo "  cleanup            Remove all containers and volumes"
    echo "  help               Show this help message"
    echo ""
    echo "Services:"
    echo "  mongodb            MongoDB database"
    echo "  qdrant             Qdrant vector database"
    echo "  kato-primary       Primary KATO instance"
    echo "  kato-testing       Testing KATO instance"
    echo "  kato-analytics     Analytics KATO instance"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start all services"
    echo "  $0 start kato-testing       # Start only testing instance"
    echo "  $0 logs kato-primary        # View primary instance logs"
    echo "  $0 create myinstance 8080   # Create new instance on port 8080"
}

# Main command handler
case "${1:-}" in
    build)
        build_image
        ;;
    start)
        start_services "${2:-}"
        ;;
    stop)
        stop_services "${2:-}"
        ;;
    restart)
        restart_services "${2:-}"
        ;;
    status)
        show_status
        ;;
    logs)
        view_logs "${2:-}"
        ;;
    test)
        test_fastapi
        ;;
    test-all)
        run_tests
        ;;
    create)
        create_instance "${2:-}" "${3:-}"
        ;;
    remove)
        remove_instance "${2:-}"
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        log_error "Unknown command: ${1:-}"
        show_usage
        exit 1
        ;;
esac