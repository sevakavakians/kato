#!/bin/bash

# KATO Manager Script
# Management script for KATO FastAPI architecture
# Usage: ./kato-manager.sh [command] [options]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$SCRIPT_DIR"
LOGS_DIR="$KATO_ROOT/logs"

# Docker configuration
COMPOSE_FILE="docker-compose.yml"
TEST_COMPOSE_FILE="docker-compose.test.yml"
DOCKERFILE="Dockerfile"
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

# Build Docker image
build() {
    log_info "Building KATO Docker image..."
    
    docker build -t "$DOCKER_IMAGE" -f "$DOCKERFILE" .
    
    if [ $? -eq 0 ]; then
        log_success "Build complete"
        docker images | grep kato
    else
        log_error "Build failed"
        exit 1
    fi
}

# Start services
start() {
    log_info "Starting KATO services..."
    
    docker-compose -f "$COMPOSE_FILE" up -d
    
    if [ $? -eq 0 ]; then
        log_success "Services started"
        
        # Wait for services to be healthy
        log_info "Waiting for services to be healthy..."
        sleep 5
        
        # Show status
        docker-compose -f "$COMPOSE_FILE" ps
        
        echo ""
        log_success "KATO services are running!"
        echo ""
        echo "  Primary:    http://localhost:8001"
        echo "  Testing:    http://localhost:8002"
        echo "  Analytics:  http://localhost:8003"
        echo "  MongoDB:    mongodb://localhost:27017"
        echo "  Qdrant:     http://localhost:6333"
        echo "  Redis:      redis://localhost:6379"
        echo ""
        echo "  API Docs:   http://localhost:8001/docs"
        echo ""
    else
        log_error "Failed to start services"
        exit 1
    fi
}

# Stop services
stop() {
    log_info "Stopping KATO services..."
    
    docker-compose -f "$COMPOSE_FILE" down
    
    if [ $? -eq 0 ]; then
        log_success "Services stopped"
    else
        log_error "Failed to stop services"
        exit 1
    fi
}

# Restart services
restart() {
    stop
    start
}

# Show service status
status() {
    log_info "KATO Service Status"
    echo ""
    
    # Check running containers
    echo "Running Containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "kato-|NAME"
    echo ""
    
    # Check service health
    echo "Service Health:"
    for service in kato-primary kato-testing kato-analytics; do
        if docker ps | grep -q "$service"; then
            PORT=$(docker port "$service" 8000 2>/dev/null | cut -d: -f2)
            if [ -n "$PORT" ]; then
                if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
                    echo "  ✅ $service (port $PORT): healthy"
                else
                    echo "  ❌ $service (port $PORT): not responding"
                fi
            else
                echo "  ⚠️  $service: running but port not mapped"
            fi
        else
            echo "  ⭕ $service: not running"
        fi
    done
    echo ""
    
    # Database status
    echo "Database Status:"
    if docker ps | grep -q "kato-mongodb"; then
        echo "  ✅ MongoDB: running"
    else
        echo "  ❌ MongoDB: not running"
    fi
    
    if docker ps | grep -q "kato-qdrant"; then
        echo "  ✅ Qdrant: running"
    else
        echo "  ❌ Qdrant: not running"
    fi
    
    if docker ps | grep -q "kato-redis"; then
        echo "  ✅ Redis: running"
    else
        echo "  ❌ Redis: not running"
    fi
}

# View logs
logs() {
    SERVICE="${1:-}"
    
    if [ -z "$SERVICE" ]; then
        log_info "Viewing all service logs (last 50 lines)..."
        docker-compose -f "$COMPOSE_FILE" logs --tail=50
    else
        log_info "Viewing logs for $SERVICE (following)..."
        docker-compose -f "$COMPOSE_FILE" logs -f "$SERVICE"
    fi
}

# Clean up volumes and data
clean() {
    log_warning "This will remove all KATO containers, volumes, and data!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up KATO..."
        
        # Stop services
        docker-compose -f "$COMPOSE_FILE" down -v
        
        # Remove images
        docker rmi "$DOCKER_IMAGE" 2>/dev/null || true
        
        # Clean up logs
        rm -f "$LOGS_DIR"/*.log
        
        log_success "Cleanup complete"
    else
        log_info "Cleanup cancelled"
    fi
}

# Run tests
test() {
    log_info "Running KATO tests..."
    
    # Build test image if needed
    docker-compose -f "$TEST_COMPOSE_FILE" build
    
    # Start test services
    docker-compose -f "$TEST_COMPOSE_FILE" up -d
    
    # Wait for services
    log_info "Waiting for test services to be ready..."
    sleep 10
    
    # Run tests
    log_info "Executing test suite..."
    docker exec kato-test python -m pytest tests/ -v
    
    # Stop test services
    docker-compose -f "$TEST_COMPOSE_FILE" down
    
    log_success "Tests complete"
}

# Show help
show_help() {
    cat << EOF
KATO Manager - Docker Service Management

Usage: $0 [command] [options]

Commands:
  build              Build Docker image
  start              Start all services
  stop               Stop all services
  restart            Restart all services
  status             Show service status
  logs [service]     View service logs
  test               Run test suite
  clean              Clean up all data and volumes
  help               Show this help message

Examples:
  $0 start           Start all services
  $0 logs kato-primary    View primary service logs
  $0 status          Check service health

Services:
  kato-primary       Primary KATO instance
  kato-testing       Testing KATO instance
  kato-analytics     Analytics KATO instance
  mongodb            MongoDB database
  qdrant             Qdrant vector database
  redis              Redis session store

EOF
}

# Main execution
check_docker

case "${1:-}" in
    build)
        build
        ;;
    start|up)
        start
        ;;
    stop|down)
        stop
        ;;
    restart)
        restart
        ;;
    status|ps)
        status
        ;;
    logs|log)
        logs "${2:-}"
        ;;
    test)
        test
        ;;
    clean)
        clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -n "${1:-}" ]; then
            log_error "Unknown command: $1"
        fi
        show_help
        exit 1
        ;;
esac