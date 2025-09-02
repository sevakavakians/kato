#!/bin/bash

# KATO Clustered Test Harness
# Runs tests in clusters with complete isolation between different configurations

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
CLUSTER_ORCHESTRATOR="${SCRIPT_DIR}/cluster-orchestrator.sh"
KATO_MANAGER="${SCRIPT_DIR}/kato-manager.sh"
TEST_OUTPUT_DIR="${SCRIPT_DIR}/logs/test-runs"
TEST_IMAGE_NAME="kato-test-harness"

# Flags (can be overridden by command line)
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

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not found"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is required but not found"
        exit 1
    fi
    
    # Check if cluster orchestrator exists
    if [[ ! -f "$CLUSTER_ORCHESTRATOR" ]]; then
        log_error "cluster-orchestrator.sh not found at $CLUSTER_ORCHESTRATOR"
        exit 1
    fi
    
    # Check if kato-manager.sh exists
    if [[ ! -f "$KATO_MANAGER" ]]; then
        log_error "kato-manager.sh not found at $KATO_MANAGER"
        exit 1
    fi
    
    # Check if test harness container exists
    if ! docker images -q "$TEST_IMAGE_NAME:latest" &> /dev/null; then
        log_warning "Test harness container not built. Building now..."
        docker build -f Dockerfile.test -t "$TEST_IMAGE_NAME:latest" . || {
            log_error "Failed to build test harness"
            exit 1
        }
    fi
    
    log_success "Prerequisites check complete"
}

# Function to ensure network exists
ensure_network() {
    # Ensure network exists
    docker network create kato-network 2>/dev/null || true
    log_success "Network is ready"
}

# Function to cleanup orphaned test data
cleanup_orphaned_data() {
    # Skip cleanup on host - dependencies only exist in containers
    # Cleanup happens automatically when containers are removed
    log_info "Skipping orphaned data cleanup (handled by container lifecycle)"
    return 0
}

# Function to run clustered tests
run_clustered_tests() {
    local test_path="${1:-}"
    
    # Create output directory
    mkdir -p "$TEST_OUTPUT_DIR"
    
    # Generate timestamp for this run
    local TEST_TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    local output_file="${TEST_OUTPUT_DIR}/clustered-output-${TEST_TIMESTAMP}.log"
    local summary_file="${TEST_OUTPUT_DIR}/clustered-summary-${TEST_TIMESTAMP}.txt"
    
    log_info "Starting clustered test execution..."
    
    # Set environment variables for orchestrator
    export VERBOSE="$VERBOSE_OUTPUT"
    export NO_REDIRECT="$NO_REDIRECT"
    
    # Check if we should bypass file redirection
    if [[ "$NO_REDIRECT" == "true" ]]; then
        log_info "Running tests with direct console output (--no-redirect mode)..."
        
        # Run orchestrator directly without file redirection, passing test path
        "$CLUSTER_ORCHESTRATOR" run "$test_path"
        
        local exit_code=$?
    elif [[ "$VERBOSE_OUTPUT" == "true" ]]; then
        log_info "Running tests in verbose mode..."
        log_info "Output will be saved to: $output_file"
        
        # Run with verbose output to both console and file, passing test path
        "$CLUSTER_ORCHESTRATOR" run "$test_path" 2>&1 | tee "$output_file"
        
        local exit_code=${PIPESTATUS[0]}
    else
        log_info "Output will be saved to: $output_file"
        log_info "Running tests (use --verbose to see progress)..."
        
        # Run with output to file, showing only key lines, passing test path
        "$CLUSTER_ORCHESTRATOR" run "$test_path" 2>&1 | \
            tee "$output_file" | \
            grep -E "^(\[.*\]|Progress:|Total Results:|CLUSTER ORCHESTRATION|Passed:|Failed:|Skipped:|✓)" || true
        
        local exit_code=${PIPESTATUS[0]}
    fi
    
    # Generate summary
    echo "CLUSTERED TEST RUN SUMMARY" > "$summary_file"
    echo "=========================" >> "$summary_file"
    echo "Timestamp: $(date)" >> "$summary_file"
    echo "Exit Code: $exit_code" >> "$summary_file"
    echo "" >> "$summary_file"
    
    # Extract results from output
    grep -E "(Passed:|Failed:|Skipped:|Duration:)" "$output_file" | tail -4 >> "$summary_file" || true
    
    # Show summary
    echo ""
    cat "$summary_file"
    echo ""
    echo "Full output saved to: $output_file"
    echo "Summary saved to: $summary_file"
    
    return $exit_code
}

# Function to stop all test instances and their databases
stop_all_test_instances() {
    log_info "Stopping all test KATO instances and databases..."
    
    # Stop KATO containers and extract their IDs for database cleanup
    docker ps -a --format "{{.Names}}" | grep -E "^kato-(test_|cluster_)" | while read container; do
        # Extract the ID suffix from the container name
        local instance_id="${container#kato-}"
        log_info "Stopping instance: $instance_id"
        
        # Stop and remove KATO container
        docker stop "$container" 2>/dev/null || true
        docker rm "$container" 2>/dev/null || true
        
        # Stop and remove associated databases
        docker stop "mongo-${instance_id}" 2>/dev/null || true
        docker rm "mongo-${instance_id}" 2>/dev/null || true
        docker stop "qdrant-${instance_id}" 2>/dev/null || true
        docker rm "qdrant-${instance_id}" 2>/dev/null || true
        docker stop "redis-${instance_id}" 2>/dev/null || true
        docker rm "redis-${instance_id}" 2>/dev/null || true
    done
    
    # Also clean up any orphaned database containers
    docker ps -a --format "{{.Names}}" | grep -E "^(mongo|qdrant|redis)-(test_|cluster_)" | while read container; do
        log_info "Removing orphaned database: $container"
        docker stop "$container" 2>/dev/null || true
        docker rm "$container" 2>/dev/null || true
    done
    
    log_success "All test instances and databases stopped"
}

# Main script logic
print_usage() {
    echo "KATO Clustered Test Harness"
    echo ""
    echo "Usage: $0 [options] [command] [args]"
    echo ""
    echo "Commands:"
    echo "  run [path]      Run tests with clustering (default: all tests)"
    echo "  cleanup         Clean up orphaned test data"
    echo "  stop            Stop all test instances"
    echo "  status          Show status of services and instances"
    echo "  help            Show this help message"
    echo ""
    echo "Options:"
    echo "  --verbose       Show full test output in terminal"
    echo "  --no-redirect   Show output directly in terminal (no file saving)"
    echo ""
    echo "Examples:"
    echo "  $0 run                    # Run all tests with clustering"
    echo "  $0 --verbose run          # Run tests with verbose output"
    echo "  $0 --no-redirect run      # Run tests with direct console output"
    echo "  $0 run tests/unit/        # Run unit tests with clustering"
    echo "  $0 cleanup                # Clean orphaned test data"
    echo "  $0 stop                   # Stop all test instances"
}

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE_OUTPUT=true
            shift
            ;;
        --no-redirect)
            NO_REDIRECT=true
            shift
            ;;
        --*)
            # Unknown option
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
        *)
            # Not an option, must be a command
            break
            ;;
    esac
done

# Parse command
case "${1:-help}" in
    run)
        shift
        check_prerequisites
        ensure_network
        cleanup_orphaned_data
        run_clustered_tests "$@"
        ;;
    cleanup)
        cleanup_orphaned_data
        ;;
    stop)
        stop_all_test_instances
        ;;
    status)
        log_info "Service Status:"
        docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(mongo-kb|qdrant|redis-cache|kato-)" || echo "No services running"
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