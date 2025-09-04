#!/bin/bash

# Simple test runner for KATO
# No Docker, no containers, just Python and pytest

set -e

echo "========================================="
echo "KATO Simple Test Runner"
echo "========================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
TEST_PATH=""
VERBOSE=""
START_KATO=true
STOP_KATO=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-start)
            START_KATO=false
            shift
            ;;
        --no-stop)
            STOP_KATO=false
            shift
            ;;
        -v|--verbose)
            VERBOSE="-vv"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [TEST_PATH]"
            echo ""
            echo "Options:"
            echo "  --no-start    Don't start KATO (assumes it's already running)"
            echo "  --no-stop     Don't stop KATO after tests"
            echo "  -v, --verbose Show verbose test output"
            echo "  -h, --help    Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                          # Run all tests"
            echo "  $0 tests/tests/unit/                       # Run unit tests"
            echo "  $0 tests/tests/unit/test_observations.py   # Run specific test file"
            echo "  $0 --no-start --no-stop                    # Run tests with existing KATO"
            exit 0
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Default to all tests if no path specified
if [ -z "$TEST_PATH" ]; then
    TEST_PATH="tests/tests/"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    pip install -q -r tests/requirements.txt
else
    source venv/bin/activate
fi

# Start KATO if requested
if [ "$START_KATO" = true ]; then
    echo -e "${GREEN}Starting KATO...${NC}"
    ./kato-manager.sh start
    
    # Wait for KATO to be ready
    echo "Waiting for KATO to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/kato-api/ping > /dev/null 2>&1; then
            echo -e "${GREEN}KATO is ready!${NC}"
            break
        fi
        sleep 1
    done
fi

# Set environment variables to disable container mode
export KATO_TEST_MODE=local
export KATO_CLUSTER_MODE=false

# Run tests
echo
echo -e "${GREEN}Running tests: $TEST_PATH${NC}"
echo "========================================="

# Add project to Python path
export PYTHONPATH="${PWD}:${PWD}/tests:$PYTHONPATH"

# Run pytest with appropriate options
if [ -n "$VERBOSE" ]; then
    python -m pytest "$TEST_PATH" $VERBOSE --tb=short --color=yes
else
    python -m pytest "$TEST_PATH" -v --tb=short --color=yes
fi

TEST_RESULT=$?

# Stop KATO if requested
if [ "$STOP_KATO" = true ]; then
    echo
    echo -e "${GREEN}Stopping KATO...${NC}"
    ./kato-manager.sh stop
fi

# Report results
echo
echo "========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed!${NC}"
fi
echo "========================================="

exit $TEST_RESULT