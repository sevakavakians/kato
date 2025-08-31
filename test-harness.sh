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
TEST_OUTPUT_DIR="${SCRIPT_DIR}/logs/test-runs"
MAX_OUTPUT_LINES=50000  # Maximum lines to keep in output file

# Service management flags (can be overridden by command line)
START_SERVICES=${START_SERVICES:-true}
STOP_SERVICES=${STOP_SERVICES:-true}
VERBOSE_OUTPUT=${VERBOSE_OUTPUT:-false}
NO_REDIRECT=${NO_REDIRECT:-false}

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

# Function to generate test summary from output
generate_test_summary() {
    local output_file="$1"
    local summary_file="$2"
    local errors_file="$3"
    
    # Extract test results
    local total_tests=$(grep -E "^[0-9]+ (passed|failed|skipped)" "$output_file" | tail -1 | awk '{print $1}')
    local passed=$(grep -oE "[0-9]+ passed" "$output_file" | tail -1 | awk '{print $1}')
    local failed=$(grep -oE "[0-9]+ failed" "$output_file" | tail -1 | awk '{print $1}')
    local skipped=$(grep -oE "[0-9]+ skipped" "$output_file" | tail -1 | awk '{print $1}')
    local duration=$(grep -E "in [0-9.]+s" "$output_file" | tail -1 | grep -oE "[0-9.]+s")
    local exit_code=$4
    
    # Default values if not found
    total_tests=${total_tests:-0}
    passed=${passed:-0}
    failed=${failed:-0}
    skipped=${skipped:-0}
    duration=${duration:-"unknown"}
    
    # Generate summary
    cat > "$summary_file" <<EOF
TEST RUN SUMMARY
================
Start Time: $(date -r "$output_file" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date "+%Y-%m-%d %H:%M:%S")
End Time: $(date "+%Y-%m-%d %H:%M:%S")
Duration: $duration
Exit Code: $exit_code

RESULTS
-------
Total: $total_tests tests
Passed: $passed
Failed: $failed
Skipped: $skipped

FAILED TESTS
------------
EOF
    
    # Extract failed test names
    grep "FAILED" "$output_file" | grep -E "test_.*::test_" | head -20 >> "$summary_file" || echo "None" >> "$summary_file"
    
    echo "" >> "$summary_file"
    echo "Full output: $output_file" >> "$summary_file"
    echo "Errors only: $errors_file" >> "$summary_file"
    
    # Extract errors to separate file
    grep -E "(ERROR|FAILED|AssertionError|Exception|Traceback)" "$output_file" > "$errors_file" || touch "$errors_file"
}

# Function to update latest symlinks
update_latest_symlinks() {
    local timestamp="$1"
    local output_dir="$2"
    local latest_dir="${output_dir}/latest"
    
    # Remove old symlinks
    rm -f "${latest_dir}/output.log" "${latest_dir}/summary.txt" "${latest_dir}/errors.log"
    
    # Create new symlinks
    ln -sf "../test-output-${timestamp}.log" "${latest_dir}/output.log"
    ln -sf "../test-summary-${timestamp}.txt" "${latest_dir}/summary.txt"
    ln -sf "../test-errors-${timestamp}.log" "${latest_dir}/errors.log"
}

# Function to rotate old logs
rotate_test_logs() {
    local output_dir="$1"
    
    # Delete logs older than 7 days
    find "$output_dir" -name "test-*.log" -mtime +7 -delete 2>/dev/null || true
    find "$output_dir" -name "test-*.txt" -mtime +7 -delete 2>/dev/null || true
    
    # Compress logs older than 1 day
    find "$output_dir" -name "test-*.log" -mtime +1 ! -name "*.gz" -exec gzip {} \; 2>/dev/null || true
    
    # Keep only 20 most recent test runs (counting by output files)
    ls -t "$output_dir"/test-output-*.log* 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true
    ls -t "$output_dir"/test-summary-*.txt* 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true
    ls -t "$output_dir"/test-errors-*.log* 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true
}

# Function to run tests in the container
run_tests() {
    local test_path="${1:-tests/}"
    shift || true
    local extra_args="$*"
    
    # Check if we should bypass redirection entirely
    if [[ "$NO_REDIRECT" == "true" ]]; then
        log_info "Running tests with direct console output (--no-redirect mode)..."
        log_info "Test path: $test_path"
        run_tests_direct "$test_path" $extra_args
        return $?
    fi
    
    # Setup output files
    local TEST_TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    mkdir -p "$TEST_OUTPUT_DIR/latest"
    local output_file="${TEST_OUTPUT_DIR}/test-output-${TEST_TIMESTAMP}.log"
    local summary_file="${TEST_OUTPUT_DIR}/test-summary-${TEST_TIMESTAMP}.txt"
    local errors_file="${TEST_OUTPUT_DIR}/test-errors-${TEST_TIMESTAMP}.log"
    
    # Rotate old logs before starting
    log_info "Rotating old test logs..."
    rotate_test_logs "$TEST_OUTPUT_DIR"
    
    log_info "Running tests in containerized environment..."
    log_info "Test path: $test_path"
    log_info "Output will be saved to: $output_file"
    log_info "Summary will be saved to: $summary_file"
    
    if [[ "$VERBOSE_OUTPUT" == "true" ]]; then
        log_info "Verbose mode enabled - showing full output in terminal"
    fi
    
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
    
    # Run tests with proper volume mounts and network, redirect output to file
    # Use tee to save to file while still showing progress indicator
    echo "Starting test execution..." | tee "$output_file"
    echo "Test path: $test_path" | tee -a "$output_file"
    echo "Timestamp: $(date)" | tee -a "$output_file"
    echo "=====================================" | tee -a "$output_file"
    
    # Run the test and capture output
    # Choose output mode based on VERBOSE_OUTPUT flag
    if [[ "$VERBOSE_OUTPUT" == "true" ]]; then
        # Verbose mode: show everything in terminal AND save to file
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
            run-tests "$test_path" ${extra_args:+$extra_args} 2>&1 | \
            tee "$output_file"
    else
        # Normal mode: save to file, show only key lines in terminal
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
            run-tests "$test_path" ${extra_args:+$extra_args} 2>&1 | \
            tee "$output_file" | \
            grep -E "^(test_|PASSED|FAILED|ERROR|=====|-----)" || true
    fi
    
    # Get exit code from docker (not from grep)
    local exit_code=${PIPESTATUS[0]}
    
    # Ensure container is removed
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Generate summary and update symlinks
    log_info "Generating test summary..."
    generate_test_summary "$output_file" "$summary_file" "$errors_file" $exit_code
    update_latest_symlinks "$TEST_TIMESTAMP" "$TEST_OUTPUT_DIR"
    
    # Display summary
    echo ""
    echo "================================="
    echo "TEST EXECUTION COMPLETED"
    echo "================================="
    cat "$summary_file" | head -20
    echo "================================="
    echo "Full logs saved to:"
    echo "  Output: $output_file"
    echo "  Summary: $summary_file"
    echo "  Errors: $errors_file"
    echo "  Latest: ${TEST_OUTPUT_DIR}/latest/"
    echo "================================="
    
    # Check if we need to stop services
    if [[ "$STOP_SERVICES" == "true" ]]; then
        log_info "Stopping KATO services after tests..."
        stop_kato_services
    else
        log_info "Keeping KATO services running (--no-stop flag used)"
    fi
    
    return $exit_code
}

# Function to run tests with direct console output (no file redirection)
run_tests_direct() {
    local test_path="${1:-tests/}"
    shift || true
    local extra_args="$*"
    
    log_info "Running tests with direct console output..."
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
    fi
    
    # Get processor ID and detect KATO port
    PROCESSOR_ID=""
    KATO_PORT="8000"
    
    if curl -s http://localhost:8000/connect > /dev/null 2>&1; then
        PROCESSOR_ID=$(curl -s http://localhost:8000/connect | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('genome', {}).get('id', ''))" 2>/dev/null || echo "")
        KATO_PORT="8000"
    elif curl -s http://localhost:8001/connect > /dev/null 2>&1; then
        PROCESSOR_ID=$(curl -s http://localhost:8001/connect | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('genome', {}).get('id', ''))" 2>/dev/null || echo "")
        KATO_PORT="8001"
    fi
    
    # Run tests directly to console
    docker run \
        --rm \
        --name "$TEST_CONTAINER_NAME" \
        --network "host" \
        -e MONGO_BASE_URL="${MONGO_BASE_URL:-mongodb://mongo-kb-$(whoami)-1:27017}" \
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
    
    # Setup output files (same as regular run_tests)
    local TEST_TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    mkdir -p "$TEST_OUTPUT_DIR/latest"
    local output_file="${TEST_OUTPUT_DIR}/test-output-${TEST_TIMESTAMP}.log"
    local summary_file="${TEST_OUTPUT_DIR}/test-summary-${TEST_TIMESTAMP}.txt"
    local errors_file="${TEST_OUTPUT_DIR}/test-errors-${TEST_TIMESTAMP}.log"
    
    # Rotate old logs before starting
    log_info "Rotating old test logs..."
    rotate_test_logs "$TEST_OUTPUT_DIR"
    
    log_info "Running tests in development mode (live code updates)..."
    log_info "Output will be saved to: $output_file"
    
    # Remove any existing test container
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Run with read-write mounts for development
    echo "Starting test execution (dev mode)..." | tee "$output_file"
    echo "Test path: $test_path" | tee -a "$output_file"
    echo "Timestamp: $(date)" | tee -a "$output_file"
    echo "=====================================" | tee -a "$output_file"
    
    if [[ "$VERBOSE_OUTPUT" == "true" ]]; then
        # Verbose mode: show everything
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
            run-tests "$test_path" ${extra_args:+$extra_args} 2>&1 | \
            tee -a "$output_file"
    else
        # Normal mode: limited output
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
            run-tests "$test_path" ${extra_args:+$extra_args} 2>&1 | \
            head -n $MAX_OUTPUT_LINES | \
            tee -a "$output_file"
    fi
    
    local exit_code=${PIPESTATUS[0]}
    
    # Ensure container is removed
    docker rm -f "$TEST_CONTAINER_NAME" 2>/dev/null || true
    
    # Generate summary and update symlinks
    log_info "Generating test summary..."
    generate_test_summary "$output_file" "$summary_file" "$errors_file" $exit_code
    update_latest_symlinks "$TEST_TIMESTAMP" "$TEST_OUTPUT_DIR"
    
    # Display summary
    echo ""
    echo "================================="
    echo "TEST EXECUTION COMPLETED"
    echo "================================="
    cat "$summary_file" | head -20
    echo "================================="
    echo "Full logs saved to:"
    echo "  Output: $output_file"
    echo "  Summary: $summary_file"
    echo "  Errors: $errors_file"
    echo "  Latest: ${TEST_OUTPUT_DIR}/latest/"
    echo "================================="
    
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
    echo "  --verbose       Show full test output in terminal (while still saving to file)"
    echo "  --no-redirect   Show output directly in terminal (no file redirection)"
    echo ""
    echo "Output Control:"
    echo "  Default:        Saves to file, shows progress in terminal"
    echo "  --verbose:      Shows everything in terminal AND saves to file"
    echo "  --no-redirect:  Classic mode - direct terminal output only"
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
        --verbose)
            VERBOSE_OUTPUT=true
            shift
            ;;
        --no-redirect)
            NO_REDIRECT=true
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