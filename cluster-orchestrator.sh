#!/bin/bash

# KATO Cluster Orchestrator
# Runs on host to manage KATO instances and coordinate test execution

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
KATO_MANAGER="${SCRIPT_DIR}/kato-manager.sh"
TEST_IMAGE="kato-test-harness"
TEST_DIR="${SCRIPT_DIR}/tests"
CLUSTERS_FILE="${TEST_DIR}/tests/fixtures/test_clusters.py"

# Flags
VERBOSE=${VERBOSE:-false}
NO_REDIRECT=${NO_REDIRECT:-false}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Track current KATO instance
CURRENT_PROCESSOR_ID=""
CURRENT_PORT=""

# Results tracking
TOTAL_PASSED=0
TOTAL_FAILED=0
TOTAL_SKIPPED=0
CLUSTER_RESULTS=()

# Function to generate unique processor ID
generate_processor_id() {
    local cluster_name="$1"
    local timestamp=$(date +%s%N | cut -b1-13)
    local uuid=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$(date +%s)")
    echo "cluster_${cluster_name}_${timestamp}_${uuid:0:8}"
}

# Function to find available port
find_available_port() {
    local port=8000
    while lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
        ((port++))
        if [[ $port -gt 8100 ]]; then
            log_error "No available ports found between 8000-8100"
            return 1
        fi
    done
    echo $port
}

# Function to start KATO instance
start_kato_instance() {
    local cluster_name="$1"
    local processor_id="$2"
    
    log_info "Starting KATO instance for cluster: $cluster_name"
    log_info "Processor ID: $processor_id"
    
    # Set environment variables for the kato-manager
    export PROCESSOR_ID="$processor_id"
    export PROCESSOR_NAME="ClusterProcessor_${cluster_name}"
    
    # Start KATO with explicit processor info
    PROCESSOR_ID="$processor_id" PROCESSOR_NAME="ClusterProcessor_${cluster_name}" "${KATO_MANAGER}" start >/dev/null 2>&1 || {
        log_error "Failed to start KATO instance"
        return 1
    }
    
    # Default port is 8000 but might be different if already in use
    # Check which port was actually allocated by checking the registered instance
    CURRENT_PORT=8000
    
    # Check if KATO started on a different port
    if [[ -f "$HOME/.kato/instances.json" ]]; then
        local actual_port=$(python3 -c "
import json
try:
    with open('$HOME/.kato/instances.json', 'r') as f:
        data = json.load(f)
        if '$processor_id' in data.get('instances', {}):
            print(data['instances']['$processor_id']['api_port'])
except:
    pass
" 2>/dev/null)
        if [[ -n "$actual_port" ]]; then
            CURRENT_PORT="$actual_port"
        fi
    fi
    
    # Wait for KATO to be ready
    local max_wait=30
    local waited=0
    while [[ $waited -lt $max_wait ]]; do
        if curl -s "http://localhost:${CURRENT_PORT}/kato-api/ping" >/dev/null 2>&1; then
            log_success "KATO instance ready on port $CURRENT_PORT"
            CURRENT_PROCESSOR_ID="$processor_id"
            return 0
        fi
        sleep 1
        ((waited++))
    done
    
    log_error "KATO instance did not become ready"
    # Try to get diagnostic info
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep "kato-${processor_id}" || true
    return 1
}

# Function to stop KATO instance and all associated databases
stop_kato_instance() {
    local processor_id="$1"
    
    if [[ -n "$processor_id" ]]; then
        log_info "Stopping KATO instance and databases: $processor_id"
        
        # Use kato-manager.sh to properly stop instance and all databases
        export PROCESSOR_ID="$processor_id"
        "${KATO_MANAGER}" stop "$processor_id" >/dev/null 2>&1 || {
            # Fallback: manually stop all containers if manager fails
            docker stop "kato-${processor_id}" >/dev/null 2>&1 || true
            docker rm "kato-${processor_id}" >/dev/null 2>&1 || true
            docker stop "mongo-${processor_id}" >/dev/null 2>&1 || true
            docker rm "mongo-${processor_id}" >/dev/null 2>&1 || true
            docker stop "qdrant-${processor_id}" >/dev/null 2>&1 || true
            docker rm "qdrant-${processor_id}" >/dev/null 2>&1 || true
            docker stop "redis-${processor_id}" >/dev/null 2>&1 || true
            docker rm "redis-${processor_id}" >/dev/null 2>&1 || true
        }
        
        CURRENT_PROCESSOR_ID=""
        CURRENT_PORT=""
    fi
}

# Function to apply cluster configuration
apply_cluster_config() {
    local processor_id="$1"
    local recall_threshold="$2"
    local max_pattern_length="$3"
    
    if [[ -n "$recall_threshold" ]]; then
        curl -s -X POST \
            "http://localhost:${CURRENT_PORT}/${processor_id}/genes/change" \
            -H "Content-Type: application/json" \
            -d "{\"data\": {\"recall_threshold\": $recall_threshold}}" \
            >/dev/null || log_warning "Failed to set recall_threshold"
    fi
    
    if [[ -n "$max_pattern_length" ]]; then
        curl -s -X POST \
            "http://localhost:${CURRENT_PORT}/${processor_id}/genes/change" \
            -H "Content-Type: application/json" \
            -d "{\"data\": {\"max_pattern_length\": $max_pattern_length}}" \
            >/dev/null || log_warning "Failed to set max_pattern_length"
    fi
}

# Function to clear memory
clear_memory() {
    local processor_id="$1"
    
    # Try to clear memory, but don't warn on failure (might not be implemented)
    curl -s -X POST \
        "http://localhost:${CURRENT_PORT}/${processor_id}/clear-all-memory" \
        -H "Content-Type: application/json" \
        -d "{}" \
        >/dev/null 2>&1 || true
}

# Function to run tests in container
run_tests_in_container() {
    local cluster_name="$1"
    local processor_id="$2"
    local test_paths="$3"
    
    # Get the KATO container name for network access
    local kato_container="kato-${processor_id}"
    
    # Build docker command - use kato-network instead of host network
    local docker_cmd="docker run --rm --network kato-network"
    docker_cmd="$docker_cmd -e KATO_CLUSTER_MODE=true"
    docker_cmd="$docker_cmd -e KATO_TEST_MODE=container"
    docker_cmd="$docker_cmd -e KATO_PROCESSOR_ID=$processor_id"
    # Use container name for API URL since we're on the same network
    docker_cmd="$docker_cmd -e KATO_API_URL=http://${kato_container}:8000"
    docker_cmd="$docker_cmd -e MONGO_BASE_URL=mongodb://mongo-${processor_id}:27017"
    docker_cmd="$docker_cmd -e QDRANT_URL=http://qdrant-${processor_id}:6333"
    docker_cmd="$docker_cmd -e REDIS_URL=redis://redis-${processor_id}:6379"
    docker_cmd="$docker_cmd -e VERBOSE_OUTPUT=$VERBOSE"
    docker_cmd="$docker_cmd -v ${TEST_DIR}:/tests:ro"
    docker_cmd="$docker_cmd ${TEST_IMAGE}:latest"
    docker_cmd="$docker_cmd python3 /tests/run_cluster_tests.py"
    docker_cmd="$docker_cmd --cluster \"$cluster_name\""
    docker_cmd="$docker_cmd --processor-id \"$processor_id\""
    docker_cmd="$docker_cmd --tests \"$test_paths\""
    
    if [[ "$VERBOSE" == "true" ]]; then
        docker_cmd="$docker_cmd --verbose"
    fi
    
    # Debug: Show the command being executed
    if [[ "$VERBOSE" == "true" ]]; then
        echo "Executing: $docker_cmd"
    fi
    
    # Run tests and capture output
    local output
    output=$(eval $docker_cmd 2>&1) || true
    
    # Parse results - look for the final summary line
    local summary_line=$(echo "$output" | grep -E '^[0-9]+ passed, [0-9]+ failed, [0-9]+ skipped$' | tail -1)
    
    if [[ -n "$summary_line" ]]; then
        # Extract counts from summary line
        local passed=$(echo "$summary_line" | awk '{print $1}')
        local failed=$(echo "$summary_line" | awk '{print $3}')
        local skipped=$(echo "$summary_line" | awk '{print $5}')
        
        if [[ "$VERBOSE" == "true" ]]; then
            echo "[DEBUG] Found summary line: $summary_line"
            echo "[DEBUG] Parsed: passed=$passed, failed=$failed, skipped=$skipped"
        fi
    else
        # Fallback to grep method
        local passed=$(echo "$output" | grep -oE '[0-9]+ passed' | awk '{print $1}' | tail -1)
        local failed=$(echo "$output" | grep -oE '[0-9]+ failed' | awk '{print $1}' | tail -1)
        local skipped=$(echo "$output" | grep -oE '[0-9]+ skipped' | awk '{print $1}' | tail -1)
        
        if [[ "$VERBOSE" == "true" ]]; then
            echo "[DEBUG] Using fallback parsing"
            echo "[DEBUG] Parsed: passed=$passed, failed=$failed, skipped=$skipped"
        fi
    fi
    
    # Default to 0 if parsing failed
    passed=${passed:-0}
    failed=${failed:-0}
    skipped=${skipped:-0}
    
    # Update totals
    TOTAL_PASSED=$((TOTAL_PASSED + passed))
    TOTAL_FAILED=$((TOTAL_FAILED + failed))
    TOTAL_SKIPPED=$((TOTAL_SKIPPED + skipped))
    
    if [[ "$VERBOSE" == "true" ]]; then
        echo "[DEBUG] Updated totals: TOTAL_PASSED=$TOTAL_PASSED, TOTAL_FAILED=$TOTAL_FAILED, TOTAL_SKIPPED=$TOTAL_SKIPPED"
    fi
    
    # Show output based on verbosity
    if [[ "$VERBOSE" == "true" ]] || [[ "$NO_REDIRECT" == "true" ]]; then
        echo "$output"
    else
        # Show compact summary
        if [[ $failed -gt 0 ]]; then
            echo "  ✗ ${passed}P/${failed}F/${skipped}S"
        elif [[ $skipped -gt 0 ]]; then
            echo "  ⚠ ${passed}P/${failed}F/${skipped}S"
        else
            echo "  ✓ ${passed}P"
        fi
    fi
    
    return 0
}

# Function to get cluster definitions
get_clusters() {
    # Extract cluster information from Python file, applying filter if provided
    python3 -c "
import sys
sys.path.insert(0, '${TEST_DIR}/tests')
from fixtures.test_clusters import TEST_CLUSTERS
import json

test_filter = '${TEST_PATH_FILTER}'
clusters = []
for cluster in TEST_CLUSTERS:
    # Filter tests if a path filter is provided
    if test_filter:
        # Support partial matches - check if any test pattern contains the filter or vice versa
        filtered_tests = [t for t in cluster.test_patterns 
                         if test_filter in t or t in test_filter or 
                         (test_filter.replace('tests/', '') in t) or
                         (t.replace('tests/', '') in test_filter)]
        if not filtered_tests:
            continue  # Skip cluster if no tests match
    else:
        filtered_tests = cluster.test_patterns
    
    clusters.append({
        'name': cluster.name,
        'recall_threshold': cluster.config.get('recall_threshold', 0.1),
        'max_pattern_length': cluster.config.get('max_pattern_length', 0),
        'tests': filtered_tests,
        'description': cluster.description
    })
print(json.dumps(clusters))
" 2>/dev/null || echo "[]"
}

# Function to run a single cluster
run_cluster() {
    local cluster_json="$1"
    
    # Parse cluster info
    local name=$(echo "$cluster_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['name'])")
    local recall=$(echo "$cluster_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['recall_threshold'])")
    local max_len=$(echo "$cluster_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['max_pattern_length'])")
    local tests=$(echo "$cluster_json" | python3 -c "import sys, json; print(' '.join(json.load(sys.stdin)['tests']))")
    local desc=$(echo "$cluster_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['description'])")
    
    if [[ "$VERBOSE" == "true" ]]; then
        echo ""
        echo "============================================================"
        echo "Cluster: $name"
        echo "Description: $desc"
        echo "Configuration: recall_threshold=$recall, max_pattern_length=$max_len"
        echo "Test count: $(echo $tests | wc -w)"
        echo "============================================================"
    else
        local test_count=$(echo $tests | wc -w)
        echo -n "[$name] Starting (${test_count} tests)..."
    fi
    
    # Generate processor ID
    local processor_id=$(generate_processor_id "$name")
    
    # Start KATO instance
    if ! start_kato_instance "$name" "$processor_id"; then
        log_error "Failed to start KATO for cluster $name"
        CLUSTER_RESULTS+=("$name: FAILED TO START")
        return 1
    fi
    
    # Apply configuration
    apply_cluster_config "$processor_id" "$recall" "$max_len"
    
    # Run tests with memory clearing between each
    local test_count=0
    local total_tests=$(echo $tests | wc -w)
    
    for test in $tests; do
        test_count=$((test_count + 1))
        
        # Clear memory before each test
        clear_memory "$processor_id"
        
        # Run the test
        if [[ "$VERBOSE" == "true" ]]; then
            echo "  Running test $test_count/$total_tests: $test"
        else
            echo -n "."
        fi
        
        run_tests_in_container "$name" "$processor_id" "$test"
    done
    
    # Stop KATO instance and all databases
    stop_kato_instance "$processor_id"
    
    # Show cluster completion
    if [[ "$VERBOSE" != "true" ]]; then
        echo " Done!"
    else
        echo "Cluster $name completed."
    fi
    
    # Track results - don't try to use $output since it doesn't exist here
    # The totals are already accumulated in run_tests_in_container
    CLUSTER_RESULTS+=("$name: completed")
    
    return 0
}

# Main execution
main() {
    log_info "KATO Cluster Orchestrator Starting"
    
    # Show test path filter if provided
    if [[ -n "$TEST_PATH_FILTER" ]]; then
        log_info "Test path filter: $TEST_PATH_FILTER"
    fi
    
    # Check prerequisites
    if [[ ! -f "$KATO_MANAGER" ]]; then
        log_error "kato-manager.sh not found"
        exit 1
    fi
    
    if ! docker images -q "$TEST_IMAGE:latest" >/dev/null 2>&1; then
        log_warning "Test harness image not found, building..."
        docker build -f Dockerfile.test -t "$TEST_IMAGE:latest" . || {
            log_error "Failed to build test harness"
            exit 1
        }
    fi
    
    # Get cluster definitions
    log_info "Loading cluster definitions..."
    local clusters_json=$(get_clusters)
    
    if [[ "$clusters_json" == "[]" ]]; then
        log_error "No cluster definitions found"
        exit 1
    fi
    
    local num_clusters=$(echo "$clusters_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
    log_info "Found $num_clusters test clusters"
    
    if [[ "$VERBOSE" != "true" ]]; then
        echo -n "Progress: "
    fi
    
    # Run each cluster
    # Use process substitution to avoid subshell issues with variable updates
    while IFS= read -r cluster_json; do
        run_cluster "$cluster_json"
    done < <(echo "$clusters_json" | python3 -c "
import sys, json
clusters = json.load(sys.stdin)
for cluster in clusters:
    print(json.dumps(cluster))
")
    
    # Print detailed summary
    echo ""
    echo "============================================================"
    echo "CLUSTER ORCHESTRATION COMPLETE"
    echo "============================================================"
    echo ""
    echo "Cluster Results:"
    echo "----------------"
    for result in "${CLUSTER_RESULTS[@]}"; do
        echo "  $result"
    done
    echo ""
    echo "Total Results:"
    echo "--------------"
    echo "  ✓ Passed:  $TOTAL_PASSED"
    if [[ $TOTAL_FAILED -gt 0 ]]; then
        echo "  ✗ Failed:  $TOTAL_FAILED"
    else
        echo "  ✗ Failed:  $TOTAL_FAILED"
    fi
    if [[ $TOTAL_SKIPPED -gt 0 ]]; then
        echo "  ⚠ Skipped: $TOTAL_SKIPPED"
    else
        echo "  ⚠ Skipped: $TOTAL_SKIPPED"
    fi
    echo ""
    
    # Show success/failure message
    if [[ $TOTAL_FAILED -gt 0 ]]; then
        log_error "Tests failed! ($TOTAL_FAILED failures)"
        exit 1
    elif [[ $TOTAL_PASSED -eq 0 ]]; then
        log_warning "No tests passed. Check test configuration."
        exit 1
    else
        log_success "All tests passed! ($TOTAL_PASSED passed)"
        exit 0
    fi
}

# Handle arguments
TEST_PATH_FILTER=""
case "${1:-run}" in
    run)
        shift || true
        # Accept optional test path filter
        TEST_PATH_FILTER="${1:-}"
        main
        ;;
    --help|-h)
        echo "KATO Cluster Orchestrator"
        echo "Usage: $0 [run] [test_path]"
        echo ""
        echo "Arguments:"
        echo "  test_path    Optional path to filter tests (e.g., tests/unit/)"
        echo ""
        echo "Environment Variables:"
        echo "  VERBOSE=true     Show detailed output"
        echo "  NO_REDIRECT=true Show all test output"
        ;;
    *)
        log_error "Unknown command: $1"
        exit 1
        ;;
esac