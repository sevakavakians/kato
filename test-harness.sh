#!/bin/bash

# KATO Test Harness Manager
# Portable testing solution using Docker containers

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
TEST_IMAGE_NAME="kato-test-harness"
TEST_CONTAINER_NAME="kato-test-runner"
DOCKER_NETWORK="kato-network"
KATO_MANAGER="${SCRIPT_DIR}/kato-manager.sh"

# Service management flags (can be overridden by command line)
START_SERVICES=${START_SERVICES:-true}
STOP_SERVICES=${STOP_SERVICES:-true}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to check if KATO services are running
check_kato_services() {
    local mongo_running=false
    local redis_running=false
    local qdrant_running=false
    local kato_running=false
    
    # Check MongoDB
    if docker ps --format "table {{.Names}}" | grep -q "mongo-kb"; then
        mongo_running=true
    fi
    
    # Check Redis
    if docker ps --format "table {{.Names}}" | grep -q "redis-cache"; then
        redis_running=true
    fi
    
    # Check Qdrant
    if docker ps --format "table {{.Names}}" | grep -q "qdrant"; then
        qdrant_running=true
    fi
    
    # Check KATO API
    if docker ps --format "table {{.Names}}" | grep -q "kato-api"; then
        kato_running=true
    fi
    
    if [[ "$mongo_running" == "true" && "$redis_running" == "true" && 
          "$qdrant_running" == "true" && "$kato_running" == "true" ]]; then
        return 0  # All services running
    else
        return 1  # Some services not running
    fi
}

# Function to start KATO services
start_kato_services() {
    log_info "Starting KATO services..."
    
    # Check if kato-manager.sh exists
    if [[ ! -f "$KATO_MANAGER" ]]; then
        log_error "kato-manager.sh not found at $KATO_MANAGER"
        exit 1
    fi
    
    # Start services using kato-manager.sh
    "$KATO_MANAGER" start || {
        log_error "Failed to start KATO services"
        exit 1
    }
    
    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    local max_wait=60
    local waited=0
    
    while [[ $waited -lt $max_wait ]]; do
        if curl -s http://localhost:8000/kato-api/ping > /dev/null 2>&1; then
            log_success "KATO services are ready"
            return 0
        fi
        sleep 2
        ((waited+=2))
    done
    
    log_error "KATO services did not become ready within ${max_wait} seconds"
    return 1
}

# Function to stop KATO services
stop_kato_services() {
    log_info "Stopping KATO services..."
    
    if [[ -f "$KATO_MANAGER" ]]; then
        "$KATO_MANAGER" stop || {
            log_warning "Failed to stop KATO services cleanly"
        }
    fi
    
    log_success "KATO services stopped"
}

# Function to build the test harness container
build_test_harness() {
    log_info "Building test harness container..."
    
    docker build -f Dockerfile.test -t "$TEST_IMAGE_NAME:latest" . || {
        log_error "Failed to build test harness"
        exit 1
    }
    
    log_success "Test harness built successfully"
}

# Function to run tests in the container
run_tests() {
    local test_path="${1:-tests/}"
    shift || true
    local extra_args="$*"
    
    log_info "Running tests in containerized environment..."
    log_info "Test path: $test_path"
    
    # Check if we need to start services
    if [[ "$START_SERVICES" == "true" ]]; then
        if ! check_kato_services; then
            log_info "KATO services not fully running, starting them..."
            start_kato_services || {
                log_error "Failed to start KATO services"
                exit 1
            }
        else
            log_info "KATO services already running"
        fi
    else
        log_info "Skipping service startup (--no-start flag used)"
        if ! check_kato_services; then
            log_warning "KATO services are not fully running! Tests requiring KATO will fail."
            log_warning "Consider running without --no-start flag or start services manually."
        fi
    fi
    
    # Check if MongoDB is running (needed for integration tests)
    if docker ps --format "table {{.Names}}" | grep -q "mongo-kb"; then
        log_info "MongoDB detected, will connect for integration tests"
        MONGO_URL="mongodb://mongo-kb-$(whoami)-1:27017"
    else
        log_warning "MongoDB not running, some integration tests may fail"
        MONGO_URL=""
    fi
    
    # Remove any existing test container
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Get processor ID and detect KATO port
    PROCESSOR_ID=""
    KATO_PORT="8000"
    
    # Try port 8000 first
    if curl -s http://localhost:8000/connect > /dev/null 2>&1; then
        PROCESSOR_ID=$(curl -s http://localhost:8000/connect | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('genome', {}).get('id', ''))" 2>/dev/null || echo "")
        KATO_PORT="8000"
    # Try port 8001 if 8000 fails
    elif curl -s http://localhost:8001/connect > /dev/null 2>&1; then
        PROCESSOR_ID=$(curl -s http://localhost:8001/connect | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('genome', {}).get('id', ''))" 2>/dev/null || echo "")
        KATO_PORT="8001"
    fi
    
    if [[ -n "$PROCESSOR_ID" ]]; then
        log_info "Found running KATO processor: $PROCESSOR_ID on port $KATO_PORT"
    fi
    
    # Run tests with proper volume mounts and network
    docker run \
        --rm \
        --name "$TEST_CONTAINER_NAME" \
        --network "host" \
        -e MONGO_BASE_URL="$MONGO_URL" \
        -e KATO_USE_OPTIMIZED="${KATO_USE_OPTIMIZED:-true}" \
        -e KATO_USE_FAST_MATCHING="${KATO_USE_FAST_MATCHING:-true}" \
        -e KATO_USE_INDEXING="${KATO_USE_INDEXING:-true}" \
        -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
        -e KATO_TEST_MODE="container" \
        -e KATO_API_URL="http://localhost:$KATO_PORT" \
        -e KATO_PROCESSOR_ID="$PROCESSOR_ID" \
        -v "$SCRIPT_DIR/kato:/kato/kato:ro" \
        -v "$SCRIPT_DIR/tests:/kato/tests:ro" \
        -v /var/run/docker.sock:/var/run/docker.sock:ro \
        "$TEST_IMAGE_NAME:latest" \
        run-tests "$test_path" ${extra_args:+$extra_args}
    
    local exit_code=$?
    
    # Ensure container is removed
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Check if we need to stop services
    if [[ "$STOP_SERVICES" == "true" ]]; then
        log_info "Stopping KATO services after tests..."
        stop_kato_services
    else
        log_info "Keeping KATO services running (--no-stop flag used)"
    fi
    
    return $exit_code
}

# Function to run tests with live code updates (development mode)
run_tests_dev() {
    local test_path="${1:-tests/}"
    shift || true
    local extra_args="$*"
    
    log_info "Running tests in development mode (live code updates)..."
    
    # Remove any existing test container
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Run with read-write mounts for development
    docker run \
        --rm \
        -it \
        --name "$TEST_CONTAINER_NAME" \
        --network "$DOCKER_NETWORK" \
        -e MONGO_BASE_URL="${MONGO_BASE_URL:-mongodb://mongo-kb-$(whoami)-1:27017}" \
        -e KATO_USE_OPTIMIZED="${KATO_USE_OPTIMIZED:-true}" \
        -e KATO_USE_FAST_MATCHING="${KATO_USE_FAST_MATCHING:-true}" \
        -e KATO_USE_INDEXING="${KATO_USE_INDEXING:-true}" \
        -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
        -v "$SCRIPT_DIR/kato:/kato/kato:rw" \
        -v "$SCRIPT_DIR/tests:/kato/tests:rw" \
        "$TEST_IMAGE_NAME:latest" \
        run-tests "$test_path" ${extra_args:+$extra_args}
    
    local exit_code=$?
    
    # Ensure container is removed
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Check if we need to stop services
    if [[ "$STOP_SERVICES" == "true" ]]; then
        log_info "Stopping KATO services after tests..."
        stop_kato_services
    else
        log_info "Keeping KATO services running (--no-stop flag used)"
    fi
    
    return $exit_code
}

# Function to run interactive shell in test container
run_shell() {
    log_info "Starting interactive shell in test container..."
    
    docker run \
        --rm \
        -it \
        --name "$TEST_CONTAINER_NAME-shell" \
        --network "$DOCKER_NETWORK" \
        -e MONGO_BASE_URL="${MONGO_BASE_URL:-mongodb://mongo-kb-$(whoami)-1:27017}" \
        -e KATO_USE_OPTIMIZED="${KATO_USE_OPTIMIZED:-true}" \
        -e KATO_USE_FAST_MATCHING="${KATO_USE_FAST_MATCHING:-true}" \
        -e KATO_USE_INDEXING="${KATO_USE_INDEXING:-true}" \
        -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
        -v "$SCRIPT_DIR/kato:/kato/kato:rw" \
        -v "$SCRIPT_DIR/tests:/kato/tests:rw" \
        "$TEST_IMAGE_NAME:latest" \
        /bin/bash
}

# Function to run specific test suites
run_suite() {
    local suite="$1"
    shift || true
    local extra_args="$*"
    
    case "$suite" in
        unit)
            log_info "Running unit tests..."
            run_tests "tests/tests/unit/" $extra_args
            ;;
        integration)
            log_info "Running integration tests..."
            run_tests "tests/tests/integration/" $extra_args
            ;;
        api)
            log_info "Running API tests..."
            run_tests "tests/tests/api/" $extra_args
            ;;
        performance)
            log_info "Running performance tests..."
            run_tests "tests/tests/performance/" $extra_args
            ;;
        determinism)
            log_info "Running determinism tests..."
            run_tests "tests/tests/unit/test_determinism_preservation.py" $extra_args
            ;;
        optimizations)
            log_info "Running optimization tests..."
            run_tests "tests/test_optimizations_standalone.py" $extra_args
            ;;
        *)
            log_error "Unknown test suite: $suite"
            echo "Available suites: unit, integration, api, performance, determinism, optimizations"
            exit 1
            ;;
    esac
}

# Function to generate test report
generate_report() {
    log_info "Generating test coverage report..."
    
    docker run \
        --rm \
        --name "$TEST_CONTAINER_NAME-coverage" \
        --network "$DOCKER_NETWORK" \
        -e MONGO_BASE_URL="${MONGO_BASE_URL:-mongodb://mongo-kb-$(whoami)-1:27017}" \
        -v "$SCRIPT_DIR/kato:/kato/kato:ro" \
        -v "$SCRIPT_DIR/tests:/kato/tests:ro" \
        -v "$SCRIPT_DIR/htmlcov:/kato/htmlcov:rw" \
        "$TEST_IMAGE_NAME:latest" \
        run-tests tests/ --cov=kato --cov-report=html --cov-report=term
    
    log_success "Coverage report generated in htmlcov/"
}

# Function to clean up test artifacts
cleanup() {
    log_info "Cleaning up test artifacts..."
    
    # Remove test containers
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    docker rm -f "$TEST_CONTAINER_NAME-shell" 2>/dev/null || true
    docker rm -f "$TEST_CONTAINER_NAME-coverage" 2>/dev/null || true
    
    # Clean pytest cache
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    
    log_success "Cleanup completed"
}

# Main script logic
print_usage() {
    echo "KATO Test Harness - Portable Testing Solution"
    echo ""
    echo "Usage: $0 [options] [command] [args]"
    echo ""
    echo "Commands:"
    echo "  build           Build the test harness container"
    echo "  test [path]     Run tests (default: all tests)"
    echo "  dev [path]      Run tests in dev mode (live code updates)"
    echo "  suite <name>    Run specific test suite"
    echo "                  (unit|integration|api|performance|determinism|optimizations)"
    echo "  shell           Start interactive shell in test container"
    echo "  report          Generate test coverage report"
    echo "  clean           Clean up test artifacts"
    echo "  rebuild         Clean rebuild of test harness"
    echo "  start-services  Start KATO services only"
    echo "  stop-services   Stop KATO services only"
    echo "  check-services  Check if KATO services are running"
    echo ""
    echo "Options:"
    echo "  --no-start      Don't start KATO services before tests"
    echo "  --no-stop       Don't stop KATO services after tests"
    echo "  --standalone    Run only standalone tests (no KATO required)"
    echo ""
    echo "Examples:"
    echo "  $0 build                          # Build test harness"
    echo "  $0 test                           # Run all tests (auto-manages services)"
    echo "  $0 --no-stop test                 # Run tests, keep services running"
    echo "  $0 --standalone test              # Run only standalone tests"
    echo "  $0 test tests/tests/unit/         # Run unit tests"
    echo "  $0 suite unit                     # Run unit test suite"
    echo "  $0 dev tests/ -x                  # Run tests in dev mode, stop on first failure"
    echo "  $0 report                         # Generate coverage report"
    echo ""
    echo "Environment Variables:"
    echo "  KATO_USE_OPTIMIZED      Enable optimizations (default: true)"
    echo "  KATO_USE_FAST_MATCHING  Enable fast matching (default: true)"
    echo "  KATO_USE_INDEXING       Enable indexing (default: true)"
    echo "  LOG_LEVEL               Set log level (default: INFO)"
}

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-start)
            START_SERVICES=false
            shift
            ;;
        --no-stop)
            STOP_SERVICES=false
            shift
            ;;
        --standalone)
            START_SERVICES=false
            STOP_SERVICES=false
            # Override test path to standalone tests only
            STANDALONE_MODE=true
            shift
            ;;
        --*)
            # Unknown option, break and let command handler deal with it
            break
            ;;
        *)
            # Not an option, must be a command
            break
            ;;
    esac
done

# Parse command
case "${1:-help}" in
    build)
        build_test_harness
        ;;
    test)
        shift
        if [[ "$STANDALONE_MODE" == "true" ]]; then
            # Run only standalone tests
            run_tests "tests/test_optimizations_standalone.py" "$@"
        else
            run_tests "$@"
        fi
        ;;
    dev)
        shift
        run_tests_dev "$@"
        ;;
    suite)
        shift
        run_suite "$@"
        ;;
    shell)
        run_shell
        ;;
    report)
        generate_report
        ;;
    clean)
        cleanup
        ;;
    rebuild)
        cleanup
        build_test_harness
        ;;
    start-services)
        start_kato_services
        ;;
    stop-services)
        stop_kato_services
        ;;
    check-services)
        if check_kato_services; then
            log_success "All KATO services are running"
        else
            log_warning "Some KATO services are not running"
            log_info "Run '$0 start-services' to start them"
        fi
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        log_error "Unknown command: $1"
        echo ""
        print_usage
        exit 1
        ;;
esac