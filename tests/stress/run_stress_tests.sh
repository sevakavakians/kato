#!/bin/bash

# KATO Stress Test Runner Script
# Provides an easy interface to run various stress tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/stress_config.yaml"
PYTHON_CMD="${PYTHON_CMD:-python3}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}"
}

function print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

function print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

function print_error() {
    echo -e "${RED}❌ $1${NC}"
}

function show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run KATO stress tests with various scenarios.

OPTIONS:
    -t, --test TEST        Test to run (concurrent, sustained, burst, pool, memory, recovery, all)
                          Default: all
    -p, --profile PROFILE  Load profile for sustained test (light, moderate, heavy, extreme, endurance)
                          Default: moderate
    -c, --config FILE      Configuration file path
                          Default: stress_config.yaml
    -q, --quick           Run quick stress tests (reduced duration)
    -v, --verbose         Enable verbose logging
    -h, --help            Show this help message

EXAMPLES:
    # Run all stress tests
    $0

    # Run only concurrent request test
    $0 --test concurrent

    # Run sustained load test with heavy profile
    $0 --test sustained --profile heavy

    # Run quick tests with reduced duration
    $0 --quick

    # Run with custom config
    $0 --config custom_config.yaml

TESTS:
    concurrent   - Test concurrent requests from multiple users
    sustained    - Test sustained load with configurable profile
    burst        - Test burst traffic patterns
    pool         - Test connection pool exhaustion
    memory       - Test for memory leaks (long running)
    recovery     - Test error recovery mechanisms
    all          - Run all tests (default)

PROFILES (for sustained test):
    light        - Light load (10 users, 60s)
    moderate     - Moderate load (50 users, 300s)
    heavy        - Heavy load (200 users, 600s)
    extreme      - Extreme load (500 users, 300s)
    endurance    - Endurance test (25 users, 3600s)

EOF
}

function check_dependencies() {
    print_header "Checking Dependencies"
    
    # Check Python
    if ! command -v $PYTHON_CMD &> /dev/null; then
        print_error "Python3 not found. Please install Python 3.6+"
        exit 1
    fi
    print_success "Python found: $($PYTHON_CMD --version)"
    
    # Check required Python packages
    local missing_packages=()
    
    for package in requests yaml numpy; do
        if ! $PYTHON_CMD -c "import $package" 2>/dev/null; then
            missing_packages+=($package)
        fi
    done
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        print_warning "Missing Python packages: ${missing_packages[*]}"
        echo "Installing missing packages..."
        $PYTHON_CMD -m pip install ${missing_packages[*]}
    fi
    
    # Check if KATO is running
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/kato-api/ping" | grep -q "200"; then
        print_success "KATO is running"
    else
        print_warning "KATO is not running. Starting KATO..."
        # Try to start KATO
        if [ -f "${SCRIPT_DIR}/../../start.sh" ]; then
            "${SCRIPT_DIR}/../../start.sh" start
            sleep 5
        else
            print_error "Could not find start.sh to start KATO"
            exit 1
        fi
    fi
    
    # Check config file
    if [ -f "$CONFIG_FILE" ]; then
        print_success "Configuration file found: $CONFIG_FILE"
    else
        print_error "Configuration file not found: $CONFIG_FILE"
        exit 1
    fi
    
    echo ""
}

function prepare_environment() {
    print_header "Preparing Test Environment"
    
    # Create results directory
    local results_dir="${SCRIPT_DIR}/stress_test_results"
    mkdir -p "$results_dir"
    print_success "Results directory ready: $results_dir"
    
    # Check available system resources
    if command -v free &> /dev/null; then
        local mem_available=$(free -m | awk '/^Mem:/{print $7}')
        if [ "$mem_available" -lt 1000 ]; then
            print_warning "Low available memory: ${mem_available}MB (recommended: >1000MB)"
        else
            print_success "Available memory: ${mem_available}MB"
        fi
    fi
    
    echo ""
}

function run_quick_tests() {
    print_header "Running Quick Stress Tests"
    
    # Create a temporary config with reduced durations
    local quick_config="${SCRIPT_DIR}/quick_stress_config.yaml"
    
    # Copy and modify the config for quick tests
    if [ -f "$CONFIG_FILE" ]; then
        cp "$CONFIG_FILE" "$quick_config"
        
        # Use sed to reduce durations (make tests 10x faster)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS sed syntax
            sed -i '' 's/duration_seconds: [0-9]*/duration_seconds: 10/g' "$quick_config"
            sed -i '' 's/ramp_up_seconds: [0-9]*/ramp_up_seconds: 2/g' "$quick_config"
            sed -i '' 's/concurrent_users: [0-9]*/concurrent_users: 10/g' "$quick_config"
        else
            # Linux sed syntax
            sed -i 's/duration_seconds: [0-9]*/duration_seconds: 10/g' "$quick_config"
            sed -i 's/ramp_up_seconds: [0-9]*/ramp_up_seconds: 2/g' "$quick_config"
            sed -i 's/concurrent_users: [0-9]*/concurrent_users: 10/g' "$quick_config"
        fi
        
        CONFIG_FILE="$quick_config"
        print_success "Created quick test configuration"
    fi
}

function run_tests() {
    local test_type="$1"
    local profile="$2"
    
    print_header "Running Stress Tests"
    echo "Test Type: $test_type"
    echo "Profile: $profile"
    echo "Config: $CONFIG_FILE"
    echo ""
    
    # Construct Python command
    local cmd="$PYTHON_CMD ${SCRIPT_DIR}/test_stress_performance.py"
    cmd="$cmd --config $CONFIG_FILE"
    cmd="$cmd --test $test_type"
    
    if [ "$test_type" == "sustained" ]; then
        cmd="$cmd --profile $profile"
    fi
    
    # Add verbose flag if requested
    if [ "$VERBOSE" == "true" ]; then
        export PYTHONUNBUFFERED=1
    fi
    
    # Run the tests
    echo "Executing: $cmd"
    echo ""
    
    if $cmd; then
        print_success "Stress tests completed successfully!"
    else
        print_error "Stress tests failed!"
        exit 1
    fi
}

function cleanup() {
    # Remove temporary quick config if it exists
    if [ -f "${SCRIPT_DIR}/quick_stress_config.yaml" ]; then
        rm "${SCRIPT_DIR}/quick_stress_config.yaml"
    fi
}

# Parse command line arguments
TEST_TYPE="all"
PROFILE="moderate"
QUICK_MODE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--test)
            TEST_TYPE="$2"
            shift 2
            ;;
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -q|--quick)
            QUICK_MODE=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate test type
case $TEST_TYPE in
    concurrent|sustained|burst|pool|memory|recovery|all)
        ;;
    *)
        print_error "Invalid test type: $TEST_TYPE"
        show_usage
        exit 1
        ;;
esac

# Validate profile
case $PROFILE in
    light|moderate|heavy|extreme|endurance)
        ;;
    *)
        print_error "Invalid profile: $PROFILE"
        show_usage
        exit 1
        ;;
esac

# Set trap for cleanup
trap cleanup EXIT

# Main execution
print_header "KATO Stress Test Runner"
echo "Starting at: $(date)"
echo ""

# Check dependencies
check_dependencies

# Prepare environment
prepare_environment

# Apply quick mode if requested
if [ "$QUICK_MODE" == "true" ]; then
    print_warning "Quick mode enabled - using reduced test durations"
    run_quick_tests
fi

# Run the tests
run_tests "$TEST_TYPE" "$PROFILE"

echo ""
print_header "Test Execution Complete"
echo "Finished at: $(date)"
echo ""

# Show results location
results_dir="${SCRIPT_DIR}/stress_test_results"
if [ -d "$results_dir" ]; then
    echo "Results saved in: $results_dir"
    echo ""
    echo "Latest results:"
    ls -lt "$results_dir" | head -5
fi