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
    
    # Get processor ID if KATO is running
    PROCESSOR_ID=""
    if curl -s http://localhost:8000/connect > /dev/null 2>&1; then
        PROCESSOR_ID=$(curl -s http://localhost:8000/connect | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('genome', {}).get('id', ''))" 2>/dev/null || echo "")
        if [[ -n "$PROCESSOR_ID" ]]; then
            log_info "Found running KATO processor: $PROCESSOR_ID"
        fi
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
        -e KATO_API_URL="http://localhost:8000" \
        -e KATO_PROCESSOR_ID="$PROCESSOR_ID" \
        -v "$SCRIPT_DIR/kato:/kato/kato:ro" \
        -v "$SCRIPT_DIR/tests:/kato/tests:ro" \
        -v /var/run/docker.sock:/var/run/docker.sock:ro \
        "$TEST_IMAGE_NAME:latest" \
        run-tests "$test_path" ${extra_args:+$extra_args}
    
    local exit_code=$?
    
    # Ensure container is removed
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
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
    echo "Usage: $0 [command] [options]"
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
    echo ""
    echo "Examples:"
    echo "  $0 build                          # Build test harness"
    echo "  $0 test                           # Run all tests"
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

# Parse command
case "${1:-help}" in
    build)
        build_test_harness
        ;;
    test)
        shift
        run_tests "$@"
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