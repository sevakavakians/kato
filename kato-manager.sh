#!/bin/bash

# KATO Manager Script
# Management script for KATO FastAPI architecture
# Usage: ./kato-manager.sh [command] [options]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$SCRIPT_DIR"
LOGS_DIR="$KATO_ROOT/logs"

# Version selection (auto-detect or default to v2)
# Auto-detect running version based on container names
if docker ps --format "{{.Names}}" 2>/dev/null | grep -q "kato-.*-v2"; then
    # v2 containers are running
    KATO_VERSION="${KATO_VERSION:-v2}"
elif docker ps --format "{{.Names}}" 2>/dev/null | grep -q "kato-primary\|kato-testing\|kato-analytics" | grep -v "v2"; then
    # v1 containers are running
    KATO_VERSION="${KATO_VERSION:-v1}"
else
    # No containers running, default to v2 (latest version)
    KATO_VERSION="${KATO_VERSION:-v2}"
fi

# Compose files based on version
if [ "$KATO_VERSION" = "v1" ]; then
    COMPOSE_FILE="docker-compose.yml"
    DOCKERFILE="Dockerfile"
    DOCKER_IMAGE="kato:latest"
    VERSION_LABEL="v1.0"
else
    COMPOSE_FILE="docker-compose.v2.yml"
    DOCKERFILE="Dockerfile.v2"
    DOCKER_IMAGE="kato:v2"
    VERSION_LABEL="v2.0"
fi

# Test compose file based on version
if [ "$KATO_VERSION" = "v1" ]; then
    TEST_COMPOSE_FILE="docker-compose.test.yml"
else
    TEST_COMPOSE_FILE="docker-compose.test.v2.yml"
fi

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
    log_info "Building KATO $VERSION_LABEL Docker image..."
    
    cd "$KATO_ROOT"
    docker build -f "$DOCKERFILE" -t "$DOCKER_IMAGE" .
    
    if [ $? -eq 0 ]; then
        log_success "KATO $VERSION_LABEL Docker image built successfully"
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
    
    # Check for conflicting v1/v2 services
    if [ "$KATO_VERSION" = "v2" ]; then
        if docker ps | grep -q "kato-primary[^-]\|kato-testing[^-]\|kato-analytics[^-]"; then
            log_warning "KATO v1.0 services are running. Please stop them first with: KATO_VERSION=v1 $0 down"
            exit 1
        fi
    else
        if docker ps | grep -q "kato-primary-v2\|kato-testing-v2\|kato-analytics-v2"; then
            log_warning "KATO v2.0 services are running. Please stop them first with: $0 down"
            exit 1
        fi
    fi
    
    # Build image if it doesn't exist
    if ! docker images | grep -q "$DOCKER_IMAGE"; then
        log_warning "Image not found, building..."
        build_image
    fi
    
    log_info "Starting KATO $VERSION_LABEL services..."
    
    cd "$KATO_ROOT"
    
    if [ -n "$service_name" ]; then
        # Start specific service
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d "$service_name"
    else
        # Start all services based on version
        if [ "$KATO_VERSION" = "v2" ]; then
            # v2 includes Redis
            $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d mongodb qdrant redis
            sleep 5  # Wait for databases
            $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d kato-primary-v2 kato-testing-v2 kato-analytics-v2
        else
            # v1 services
            $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d mongodb qdrant
            sleep 5  # Wait for databases
            $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d kato-primary kato-testing kato-analytics
        fi
    fi
    
    if [ $? -eq 0 ]; then
        log_success "KATO $VERSION_LABEL services started"
        
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
    
    log_info "Stopping KATO $VERSION_LABEL services..."
    
    cd "$KATO_ROOT"
    
    # First try docker-compose stop
    if [ -n "$service_name" ]; then
        # Stop specific service
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" stop "$service_name" 2>/dev/null
    else
        # Stop all services
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" stop 2>/dev/null
    fi
    
    # Also try stopping containers directly if compose file issues
    if [ "$KATO_VERSION" = "v2" ]; then
        docker stop kato-primary-v2 kato-testing-v2 kato-analytics-v2 2>/dev/null || true
    else
        docker stop kato-primary kato-testing kato-analytics 2>/dev/null || true
    fi
    
    log_success "KATO $VERSION_LABEL services stopped"
}

# Down services (stop and remove containers, keep volumes)
down_services() {
    check_docker
    check_docker_compose
    
    log_info "Stopping and removing KATO $VERSION_LABEL containers..."
    
    cd "$KATO_ROOT"
    
    # Use docker-compose down without -v to keep volumes
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" down 2>/dev/null || true
    
    # Also remove containers directly if needed
    if [ "$KATO_VERSION" = "v2" ]; then
        docker rm -f kato-primary-v2 kato-testing-v2 kato-analytics-v2 2>/dev/null || true
    else
        docker rm -f kato-primary kato-testing kato-analytics 2>/dev/null || true
    fi
    
    log_success "KATO $VERSION_LABEL containers stopped and removed"
}

# Start services in test mode (single instance)
start_test_services() {
    check_docker
    check_docker_compose
    
    log_info "Starting KATO in test mode (single instance)..."
    
    cd "$KATO_ROOT"
    
    # Start services using test compose file
    if $DOCKER_COMPOSE -f "$TEST_COMPOSE_FILE" up -d; then
        log_success "KATO test instance started"
        
        # Wait for services to be ready
        log_info "Waiting for services to be ready..."
        sleep 5
        
        # Show status
        show_test_status
    else
        log_error "Failed to start test services"
        exit 1
    fi
}

# Stop test services
stop_test_services() {
    check_docker
    check_docker_compose
    
    log_info "Stopping KATO test services..."
    
    cd "$KATO_ROOT"
    
    if $DOCKER_COMPOSE -f "$TEST_COMPOSE_FILE" stop; then
        log_success "KATO test services stopped"
    else
        log_error "Failed to stop test services"
        exit 1
    fi
}

# Down test services (stop and remove)
down_test_services() {
    check_docker
    check_docker_compose
    
    log_info "Stopping and removing KATO test containers..."
    
    cd "$KATO_ROOT"
    
    if $DOCKER_COMPOSE -f "$TEST_COMPOSE_FILE" down; then
        log_success "KATO test containers stopped and removed"
    else
        log_error "Failed to remove test containers"
        exit 1
    fi
}

# Show test status
show_test_status() {
    check_docker
    
    log_info "KATO Test Instance Status:"
    echo
    
    # Show running containers
    docker ps --filter "name=kato" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
    
    echo
    log_info "Service URLs:"
    echo "  KATO Test:  http://localhost:8001"
    echo "  MongoDB:    mongodb://localhost:27017"
    echo "  Qdrant:     http://localhost:6333"
    
    # Health check
    echo
    log_info "Health Check:"
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "  Port 8001: ${GREEN}✓ Healthy${NC}"
    else
        echo -e "  Port 8001: ${RED}✗ Not responding${NC}"
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
    
    log_info "KATO $VERSION_LABEL Services Status:"
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
    if [ "$KATO_VERSION" = "v2" ]; then
        echo "  Redis:         redis://localhost:6379"
    fi
    
    echo ""
    log_info "Health Check:"
    
    # Check each service
    for port in 8001 8002 8003; do
        if [ "$KATO_VERSION" = "v2" ]; then
            # Check v2 health endpoint
            if curl -s "http://localhost:${port}/v2/health" > /dev/null 2>&1; then
                echo -e "  Port ${port}: ${GREEN}✓ Healthy (v2)${NC}"
            elif curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
                echo -e "  Port ${port}: ${GREEN}✓ Healthy${NC}"
            else
                echo -e "  Port ${port}: ${RED}✗ Not responding${NC}"
            fi
        else
            # Check v1 health endpoint
            if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
                echo -e "  Port ${port}: ${GREEN}✓ Healthy${NC}"
            else
                echo -e "  Port ${port}: ${RED}✗ Not responding${NC}"
            fi
        fi
    done
    
    if [ "$KATO_VERSION" = "v2" ]; then
        echo ""
        log_info "v2.0 Features:"
        echo "  ✅ Multi-user session isolation"
        echo "  ✅ Write concern = majority (no data loss)"
        echo "  ✅ Session management endpoints (/v2/sessions)"
        echo "  ✅ Backward compatible with v1 API"
    fi
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
    log_info "Testing KATO $VERSION_LABEL FastAPI implementation..."
    
    # Check if services are running
    if [ "$KATO_VERSION" = "v2" ]; then
        if ! curl -s "http://localhost:8001/v2/health" > /dev/null 2>&1; then
            log_warning "Services not running, starting them..."
            start_services
        fi
        # Run v2 test
        python3 "$KATO_ROOT/test_v2_quick.py"
    else
        if ! curl -s "http://localhost:8001/health" > /dev/null 2>&1; then
            log_warning "Services not running, starting them..."
            start_services
        fi
        # Run v1 test
        python3 "$KATO_ROOT/test_fastapi.py"
    fi
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
    
    log_info "Creating new KATO $VERSION_LABEL instance: $instance_name on port $port"
    
    # Determine network name based on version
    local network_name="kato-network"
    if [ "$KATO_VERSION" = "v2" ]; then
        network_name="kato-network-v2"
    fi
    
    # Run new container with version-appropriate settings
    if [ "$KATO_VERSION" = "v2" ]; then
        docker run -d \
            --name "kato-${instance_name}" \
            --network "$network_name" \
            -p "${port}:8000" \
            -e "PROCESSOR_ID=${instance_name}" \
            -e "PROCESSOR_NAME=${instance_name}" \
            -e "MONGO_BASE_URL=mongodb://mongodb:27017" \
            -e "QDRANT_HOST=qdrant" \
            -e "QDRANT_PORT=6333" \
            -e "REDIS_URL=redis://redis:6379" \
            -e "ENABLE_V2_FEATURES=true" \
            -e "LOG_LEVEL=INFO" \
            "$DOCKER_IMAGE"
    else
        docker run -d \
            --name "kato-${instance_name}" \
            --network "$network_name" \
            -p "${port}:8000" \
            -e "PROCESSOR_ID=${instance_name}" \
            -e "PROCESSOR_NAME=${instance_name}" \
            -e "MONGO_BASE_URL=mongodb://mongodb:27017" \
            -e "QDRANT_HOST=qdrant" \
            -e "QDRANT_PORT=6333" \
            -e "LOG_LEVEL=INFO" \
            "$DOCKER_IMAGE"
    fi
    
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

# Switch between v1 and v2
switch_version() {
    local target_version="${1:-}"
    
    if [ -z "$target_version" ] || { [ "$target_version" != "v1" ] && [ "$target_version" != "v2" ]; }; then
        log_error "Invalid version. Use 'v1' or 'v2'"
        exit 1
    fi
    
    log_info "Switching to KATO $target_version..."
    
    # Stop current version
    log_info "Stopping current services..."
    down_services
    
    # Switch version and start
    export KATO_VERSION="$target_version"
    
    # Reinitialize config for new version
    if [ "$KATO_VERSION" = "v1" ]; then
        COMPOSE_FILE="docker-compose.yml"
        DOCKERFILE="Dockerfile"
        DOCKER_IMAGE="kato:latest"
        VERSION_LABEL="v1.0"
    else
        COMPOSE_FILE="docker-compose.v2.yml"
        DOCKERFILE="Dockerfile.v2"
        DOCKER_IMAGE="kato:v2"
        VERSION_LABEL="v2.0"
    fi
    
    log_info "Starting KATO $VERSION_LABEL..."
    start_services
}

# Show usage information
show_usage() {
    echo "KATO FastAPI Manager (Current: $VERSION_LABEL)"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo "       KATO_VERSION=v1 $0 [command] [options]  # Use v1.0"
    echo ""
    echo "Current Version: $VERSION_LABEL"
    echo ""
    echo "Commands:"
    echo "  build              Build Docker image"
    echo "  start [service]    Start KATO services (or specific service)"
    echo "  stop [service]     Stop KATO services (or specific service)"
    echo "  down               Stop and remove containers (keep volumes)"
    echo "  restart [service]  Restart KATO services"
    echo "  status             Show status of services"
    echo "  logs [service]     View service logs"
    echo ""
    echo "Test Mode Commands (single instance):"
    echo "  test-start         Start single KATO instance for testing"
    echo "  test-stop          Stop test instance"
    echo "  test-down          Stop and remove test containers"
    echo "  test-status        Show test instance status"
    echo ""
    echo "Other Commands:"
    echo "  test               Run FastAPI tests"
    echo "  test-all           Run full test suite"
    echo "  create <name>      Create new KATO instance"
    echo "  remove <name>      Remove KATO instance"
    echo "  cleanup            Remove all containers and volumes"
    echo "  switch <version>   Switch between v1 and v2 (e.g., switch v1)"
    echo "  version            Show current version"
    echo "  help               Show this help message"
    echo ""
    echo "Version Control:"
    echo "  Auto-detects running version, defaults to v2.0 if none running"
    echo "  To force v1.0: KATO_VERSION=v1 $0 [command]"
    echo "  To force v2.0: KATO_VERSION=v2 $0 [command]"
    echo "  To switch: $0 switch v1  OR  $0 switch v2"
    echo ""
    echo "Services:"
    echo "  mongodb            MongoDB database"
    echo "  qdrant             Qdrant vector database"
    if [ "$KATO_VERSION" = "v2" ]; then
        echo "  kato-primary-v2    Primary KATO v2 instance"
        echo "  kato-testing-v2    Testing KATO v2 instance"
        echo "  kato-analytics-v2  Analytics KATO v2 instance"
    else
        echo "  kato-primary       Primary KATO v1 instance"
        echo "  kato-testing       Testing KATO v1 instance"
        echo "  kato-analytics     Analytics KATO v1 instance"
    fi
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start all services (v2.0 by default)"
    echo "  KATO_VERSION=v1 $0 start     # Start v1.0 services"
    echo "  $0 switch v1                # Switch to and start v1.0"
    echo "  $0 logs kato-primary-v2     # View v2 primary logs"
    echo "  $0 create myinstance 8080   # Create new instance on port 8080"
    echo ""
    echo "Testing v2.0:"
    echo "  python test_v2_quick.py      # Quick v2.0 test"
    echo "  python test_v2_demo.py       # Full v2.0 demo"
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
    down)
        down_services
        ;;
    test-start)
        start_test_services
        ;;
    test-stop)
        stop_test_services
        ;;
    test-down)
        down_test_services
        ;;
    test-status)
        show_test_status
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
    switch)
        switch_version "${2:-}"
        ;;
    version)
        echo "Current KATO version: $VERSION_LABEL"
        echo "To change: KATO_VERSION=v1 $0 [command]  OR  $0 switch v1"
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