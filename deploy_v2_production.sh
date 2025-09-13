#!/bin/bash

# KATO v2.0 Production Deployment Script
# This script deploys KATO v2 to production with health checks

set -e  # Exit on error

echo "========================================="
echo "KATO v2.0 Production Deployment"
echo "========================================="

# Configuration
COMPOSE_FILE="docker-compose.v2.yml"
HEALTH_CHECK_URL="http://localhost:8001/v2/health"
MAX_WAIT_TIME=60
REQUIRED_SERVICES="mongodb qdrant redis kato-primary-v2"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check if compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Docker Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

stop_existing_services() {
    log_info "Stopping any existing services..."
    docker-compose -f $COMPOSE_FILE down 2>/dev/null || true
    
    # Also stop v1 services if running
    docker-compose down 2>/dev/null || true
    
    log_info "Existing services stopped"
}

build_images() {
    log_info "Building v2 Docker images..."
    docker-compose -f $COMPOSE_FILE build
    
    if [ $? -eq 0 ]; then
        log_info "Images built successfully"
    else
        log_error "Failed to build images"
        exit 1
    fi
}

start_databases() {
    log_info "Starting database services..."
    docker-compose -f $COMPOSE_FILE up -d mongodb qdrant redis
    
    # Wait for databases to be ready
    log_info "Waiting for databases to initialize..."
    sleep 10
    
    # Check database health
    for service in mongodb qdrant redis; do
        if docker-compose -f $COMPOSE_FILE ps | grep $service | grep -q "Up"; then
            log_info "$service is running"
        else
            log_error "$service failed to start"
            exit 1
        fi
    done
}

start_kato_services() {
    log_info "Starting KATO v2 services..."
    docker-compose -f $COMPOSE_FILE up -d kato-primary-v2 kato-secondary-v2 kato-analytics-v2
    
    if [ $? -eq 0 ]; then
        log_info "KATO services started"
    else
        log_error "Failed to start KATO services"
        exit 1
    fi
}

wait_for_health() {
    log_info "Waiting for services to be healthy..."
    
    local count=0
    while [ $count -lt $MAX_WAIT_TIME ]; do
        if curl -s $HEALTH_CHECK_URL > /dev/null 2>&1; then
            local health=$(curl -s $HEALTH_CHECK_URL | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
            
            if [ "$health" = "healthy" ]; then
                log_info "Services are healthy!"
                return 0
            fi
        fi
        
        echo -n "."
        sleep 1
        count=$((count + 1))
    done
    
    log_error "Services failed to become healthy within $MAX_WAIT_TIME seconds"
    return 1
}

run_smoke_tests() {
    log_info "Running smoke tests..."
    
    # Create test session
    log_info "Creating test session..."
    SESSION_RESPONSE=$(curl -s -X POST http://localhost:8001/v2/sessions \
        -H "Content-Type: application/json" \
        -d '{"user_id": "smoke_test_user", "metadata": {"test": true}}')
    
    SESSION_ID=$(echo $SESSION_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])" 2>/dev/null)
    
    if [ -z "$SESSION_ID" ]; then
        log_error "Failed to create test session"
        return 1
    fi
    
    log_info "Test session created: $SESSION_ID"
    
    # Test observation
    log_info "Testing observation endpoint..."
    OBS_RESPONSE=$(curl -s -X POST http://localhost:8001/v2/sessions/$SESSION_ID/observe \
        -H "Content-Type: application/json" \
        -d '{"strings": ["smoke", "test"]}')
    
    OBS_STATUS=$(echo $OBS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    
    if [ "$OBS_STATUS" = "ok" ]; then
        log_info "Observation test passed"
    else
        log_error "Observation test failed"
        return 1
    fi
    
    # Clean up test session
    curl -s -X DELETE http://localhost:8001/v2/sessions/$SESSION_ID > /dev/null
    
    log_info "Smoke tests passed"
    return 0
}

show_status() {
    log_info "Deployment Status:"
    echo ""
    docker-compose -f $COMPOSE_FILE ps
    echo ""
    
    # Show health endpoint
    log_info "Health Check:"
    curl -s $HEALTH_CHECK_URL | python3 -m json.tool || log_error "Health check failed"
    echo ""
    
    # Show access URLs
    log_info "Access URLs:"
    echo "  Primary:   http://localhost:8001"
    echo "  Secondary: http://localhost:8002"
    echo "  Analytics: http://localhost:8003"
    echo "  API Docs:  http://localhost:8001/docs"
    echo ""
    
    # Show logs command
    log_info "View logs with:"
    echo "  docker-compose -f $COMPOSE_FILE logs -f"
    echo ""
}

cleanup_on_failure() {
    log_error "Deployment failed. Cleaning up..."
    docker-compose -f $COMPOSE_FILE down
    exit 1
}

# Main deployment flow
main() {
    echo "Starting deployment at $(date)"
    echo ""
    
    # Set trap for cleanup on failure
    trap cleanup_on_failure ERR
    
    # Pre-deployment checks
    check_prerequisites
    
    # Stop existing services
    stop_existing_services
    
    # Build and deploy
    build_images
    start_databases
    start_kato_services
    
    # Wait for health
    if wait_for_health; then
        log_info "Services are ready"
    else
        log_error "Health check failed"
        cleanup_on_failure
    fi
    
    # Run smoke tests
    if run_smoke_tests; then
        log_info "Smoke tests passed"
    else
        log_error "Smoke tests failed"
        cleanup_on_failure
    fi
    
    # Show final status
    show_status
    
    echo ""
    echo "========================================="
    echo -e "${GREEN}DEPLOYMENT SUCCESSFUL!${NC}"
    echo "========================================="
    echo "Deployment completed at $(date)"
    echo ""
    
    # Disable trap
    trap - ERR
}

# Run main function
main "$@"